"""End-to-end test harness: drives the real oganesson binary.

Each test class starts its own Xvfb display and a browser with a throwaway
profile and HOME, then talks to it over two DevTools protocols:

- Chrome DevTools (--remote-debugging-port) for pages, extension pages and
  their JavaScript state.
- UI DevTools (--enable-ui-devtools) for the browser's own views: toolbar
  buttons, the location bar, dialogs. It gives each view's class, properties
  (text, tooltip, visibility, enabled) and screen bounds.

Clicks on browser UI are real X11 input at a view's bounds (xdotool), so they
take the same path as a user's click.

With OGANESSON_E2E_WAYLAND=1 the browser runs on Wayland instead: labwc runs
nested in the Xvfb display (its X11 backend), so the same X11 input reaches
the browser as real Wayland pointer and keyboard events, with serials (drag
and drop starts real Wayland drags). The browser window is maximized, so its
view bounds line up with the screen.

What's here:

- BrowserTest: one Browser per test class (`browser_args`, `first_run`,
  `prefs`, `browser_env`, `debugging_pipe`, `wayland` to run on Wayland
  whatever OGANESSON_E2E_WAYLAND says); each test also fails on a crash or FATAL line.
- Browser: `start()` (restart on the same profile), `stop()` (also ends what
  the browser started under its root; the harness stops every browser left
  when it exits, also on SIGTERM or SIGHUP),
  `follow_relaunch()` (after the browser restarted itself); both return once
  the bundled uBlock Origin filters, unless the profile disables it; pages with
  `page(url_part)`, `new_tab(url)`, `close_target(page)`, `targets()`,
  `browser_call(method)`, `pipe_call(method)` (PWA); views with `views(cls, **props)`,
  `wait_view(cls, **props)`, `menus()`, `ubo_background()`, `wait_ubo_menu()`; real input with `click_view(view)`,
  `click_element(page, selector, button, repeat)`, `key(*keys)`, `xdotool(...)`;
  `root`, `profile`, `home` and `log_path` for files.
- Page: `eval(js)` (awaits promises), `click(selector, button)`, `call(method)`.
- Server: local HTTP(S) `routes`, with `requests`, `headers` and `bodies` seen.
- wait_for(check): polls until `check()` is truthy.
- installed_env(folder): `browser_env` for a browser installed as a package.

Tests to copy from: test_ubo_restart.py for the bundled uBlock Origin,
test_tab_behavior.py for a test extension loaded with --load-extension.

To explore outside a suite, run a script from tools/e2e with
OGANESSON_BINARY=../../work/helium-linux/build/src/out/Default/oganesson and
TMPDIR=../../work/tmp that starts `harness.Browser()`; add-on errors are the
`CONSOLE` lines of its `browser.log`.

Needs Python 3, Xvfb, xdotool and xwd (screen pixels), and labwc for Wayland.
Stdlib only.
"""

import atexit
import base64
import ctypes
import http.server
import json
import os
import re
import select
import shutil
import signal
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

BINARY = Path(os.environ.get('OGANESSON_BINARY', ''))
# Failed runs keep their profile and log here for inspection.
KEEP = os.environ.get('OGANESSON_E2E_KEEP') == '1'
WAYLAND = os.environ.get('OGANESSON_E2E_WAYLAND') == '1'
# Lines the dev build writes to stderr on a crash or a failed (D)CHECK.
FATAL_MARKERS = ('FATAL:', 'Check failed', 'DanglingPtr', 'Received signal')
WINDOW = (1300, 850)
# Helium's bundled uBlock Origin.
UBO = 'blockjmkbacgjkknlgpkjjiijinjdanf'
# Browsers not stopped yet, which the harness stops when it exits (#321).
BROWSERS = set()
LIBC = ctypes.CDLL(None)


def die_with_harness():
    """preexec_fn: the child gets SIGTERM when the harness dies, even by
    SIGKILL. A browser that relaunched itself isn't covered: its parent is the
    old browser."""
    LIBC.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG


def processes(text):
    """Processes whose command line contains `text`."""
    found = []
    for entry in Path('/proc').iterdir():
        try:
            if entry.name.isdigit() and text.encode() in (entry / 'cmdline').read_bytes():
                found.append(Relaunched(int(entry.name)))
        except OSError:
            continue
    return found


def end(*procs):
    """Terminates Popen or Relaunched processes, and kills those left after
    15 s. One deadline for all: detach.sh --stop kills the run after 60 s."""
    procs = [proc for proc in procs if proc.poll() is None]
    for proc in procs:
        proc.terminate()
    deadline = time.monotonic() + 15
    for proc in procs:
        try:
            proc.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# SIGTERM (detach.sh --stop) and SIGHUP end the run as Ctrl+C does, so the
# atexit handler below runs; unittest would count SystemExit as a test error.
for number in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(number, signal.default_int_handler)
# A browser still here means an interrupted run: keep its log.
atexit.register(lambda: [browser.stop(failed=True) for browser in list(BROWSERS)])


def wait_for(check, timeout=15, interval=0.2, what='condition'):
    """Polls `check` until it returns something truthy, and returns it."""
    deadline = time.monotonic() + timeout
    while True:
        value = check()
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f'timed out after {timeout}s waiting for {what}')
        time.sleep(interval)


def installed_env(folder):
    """Env for a browser that finds its .desktop file, as after a package
    install, whether or not this machine has one: it can then be the default
    browser, so onboarding asks. `folder` becomes its XDG_DATA_HOME, and a
    stub `xdg-settings` in it answers that oganesson isn't the default, so
    neither the host's xdg-utils nor its settings decide the step."""
    (folder / 'applications').mkdir(parents=True, exist_ok=True)
    (folder / 'applications/oganesson.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=oganesson\nExec=oganesson %U\n')
    (folder / 'bin').mkdir(exist_ok=True)
    (folder / 'bin/xdg-settings').write_text('#!/bin/sh\necho no\n')
    (folder / 'bin/xdg-settings').chmod(0o755)
    return {'XDG_DATA_HOME': str(folder),
            'PATH': f'{folder / "bin"}:{os.environ["PATH"]}'}


class WebSocket:
    """A minimal RFC 6455 client: text frames, no extensions."""

    def __init__(self, url, timeout=30, handshake_timeout=None):
        parts = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((parts.hostname, parts.port),
                                             timeout=handshake_timeout or timeout)
        try:
            self._handshake(url, parts, timeout)
        except BaseException:
            self.sock.close()
            raise

    def _handshake(self, url, parts, timeout):
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET {parts.path or "/"} HTTP/1.1\r\n'
                           f'Host: {parts.hostname}:{parts.port}\r\n'
                           'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                           f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        self.stream = self.sock.makefile('rb')
        status = self.stream.readline()
        if b' 101 ' not in status:
            raise ConnectionError(f'websocket upgrade to {url} failed: {status!r}')
        while self.stream.readline() not in (b'\r\n', b''):
            pass
        self.sock.settimeout(timeout)

    def send(self, text):
        data = text.encode()
        header = bytearray([0x81])
        if len(data) < 126:
            header.append(0x80 | len(data))
        elif len(data) < 1 << 16:
            header += bytes([0x80 | 126]) + struct.pack('>H', len(data))
        else:
            header += bytes([0x80 | 127]) + struct.pack('>Q', len(data))
        mask = os.urandom(4)
        self.sock.sendall(bytes(header) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        data = self.stream.read(n)
        if len(data) < n:
            raise ConnectionError('websocket closed')
        return data

    def recv(self):
        message = b''
        while True:
            first, second = self._read(2)
            length = second & 0x7f
            if length == 126:
                length = struct.unpack('>H', self._read(2))[0]
            elif length == 127:
                length = struct.unpack('>Q', self._read(8))[0]
            payload = self._read(length)
            opcode = first & 0x0f
            if opcode == 0x8:
                raise ConnectionError('websocket closed')
            if opcode in (0x9, 0xa):  # ping, pong: servers here never ping
                continue
            message += payload
            if first & 0x80:
                return message.decode()

    def close(self):
        if hasattr(self, 'stream'):
            self.stream.close()
        self.sock.close()

    __del__ = close


class Session:
    """A DevTools protocol connection. Events are kept in `events`."""

    def __init__(self, url, handshake_timeout=None):
        self.ws = WebSocket(url, handshake_timeout=handshake_timeout)
        self.next_id = 0
        self.events = []

    def call(self, method, **params):
        self.next_id += 1
        self.ws.send(json.dumps({'id': self.next_id, 'method': method, 'params': params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get('id') == self.next_id:
                if 'error' in message:
                    raise RuntimeError(f'{method}: {message["error"]}')
                return message.get('result', {})
            if 'method' in message:
                self.events.append(message)

    def close(self):
        self.ws.close()


class Page(Session):
    """A Chrome DevTools target: a tab, an extension page, a popup."""

    def __init__(self, target):
        super().__init__(target['webSocketDebuggerUrl'])
        self.id = target['id']
        self.url = target['url']

    def eval(self, expression):
        """Evaluates `expression` (awaiting a promise) and returns its value."""
        result = self.call('Runtime.evaluate', expression=expression, awaitPromise=True,
                           returnByValue=True, userGesture=True)
        if 'exceptionDetails' in result:
            details = result['exceptionDetails']
            raise AssertionError(f'{expression!r} threw: '
                                 f'{details.get("exception", {}).get("description", details)}')
        return result['result'].get('value')

    def click(self, selector, button='left'):
        """A trusted mouse click at the centre of the first match of `selector`."""
        box = self.eval(f'(() => {{ const r = document.querySelector({json.dumps(selector)})'
                        '.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()')
        for kind in ('mousePressed', 'mouseReleased'):
            self.call('Input.dispatchMouseEvent', type=kind, x=box[0], y=box[1], button=button,
                      clickCount=1)


class View:
    """A browser view from UI DevTools, with its properties at query time.
    `widget` is the node id of the widget (window, menu, bubble) it is in."""

    def __init__(self, cls, props, bounds, widget=None):
        self.cls = cls
        self.props = props
        self.bounds = bounds
        self.widget = widget

    def __getitem__(self, name):
        return self.props.get(name)

    def __repr__(self):
        return f'<{self.cls} {self.props.get("TooltipText") or self.props.get("Text") or self.props.get("Title") or ""}>'

    @property
    def visible(self):
        return self.props.get('Visible') == 'true' and self.bounds['width'] > 0

    @property
    def center(self):
        b = self.bounds
        return b['x'] + b['width'] // 2, b['y'] + b['height'] // 2


class Xvfb:
    """A private X display. Picks a free number, so parallel runs don't collide."""

    def __init__(self):
        for number in range(90, 200):
            if not (Path(f'/tmp/.X11-unix/X{number}').exists() or
                    Path(f'/tmp/.X{number}-lock').exists()):
                break
        self.display = f':{number}'
        self.proc = subprocess.Popen(
            ['Xvfb', self.display, '-screen', '0', '1400x900x24', '-nolisten', 'tcp'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=die_with_harness)
        wait_for(lambda: Path(f'/tmp/.X11-unix/X{number}').exists(), what='Xvfb')

    def stop(self):
        self.proc.terminate()
        self.proc.wait()


class Labwc:
    """labwc nested in an Xvfb display, without the user's configuration."""

    def __init__(self, xvfb, root):
        self.runtime = root / 'xdg'
        self.runtime.mkdir(mode=0o700)
        config = root / 'labwc'
        config.mkdir()
        (config / 'autostart').write_text('')
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'USER', 'LANG')}
        env.update(HOME=str(root), DISPLAY=xvfb.display, XDG_RUNTIME_DIR=str(self.runtime),
                   WLR_BACKENDS='x11', WLR_RENDERER='pixman')
        self.proc = subprocess.Popen(['labwc', '-C', str(config)], env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     preexec_fn=die_with_harness)
        wait_for(lambda: (self.runtime / 'wayland-0').exists(), what='labwc')

    def stop(self):
        self.proc.terminate()
        self.proc.wait()


class Browser:
    """The oganesson binary on an Xvfb display, with a throwaway profile and HOME."""

    def __init__(self, args=(), first_run=False, prefs=None, env=None, pipe=False,
                 wayland=WAYLAND):
        if not BINARY.is_file():
            raise unittest.SkipTest(f'no browser binary at {BINARY!s}; run ./oganesson.py build')
        # A test may start another copy of the browser on the profile.
        self.binary = BINARY
        self.root = Path(tempfile.mkdtemp(prefix='oganesson-e2e-'))
        self.profile = self.root / 'profile'
        # Downloads, caches and keyrings go under this HOME, not the user's.
        self.home = self.root / 'home'
        (self.home / 'Downloads').mkdir(parents=True)
        self.log_path = self.root / 'browser.log'
        if prefs:
            (self.profile / 'Default').mkdir(parents=True)
            (self.profile / 'Default/Preferences').write_text(json.dumps(prefs))
        self.xvfb = Xvfb()
        self.labwc = Labwc(self.xvfb, self.root) if wayland else None
        self.args = list(args) + ([] if first_run else ['--no-first-run'])
        self.extra_env = dict(env or {})
        # --remote-debugging-pipe as well, for the domains only a pipe gets
        # (PWA); see pipe_call().
        self.pipe = pipe
        self.proc = None
        self.log_offset = 0
        BROWSERS.add(self)
        try:
            self.start()
        except BaseException:
            self.stop(failed=True)
            raise

    def env(self):
        # Nothing from the user's session: no D-Bus, Wayland or desktop
        # environment, so the browser doesn't reach into it (for example, the
        # proxy settings button starts the desktop's own settings app).
        env = {k: v for k, v in os.environ.items()
               if k in ('PATH', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TZ')}
        env.update(HOME=str(self.home), DISPLAY=self.xvfb.display)
        env.update(self.extra_env)  # may set its own HOME
        if self.labwc:
            env.update(WAYLAND_DISPLAY='wayland-0', XDG_RUNTIME_DIR=str(self.labwc.runtime))
        return env

    def start(self):
        """Starts (or restarts, with the same profile) the browser."""
        for name in ('DevToolsActivePort', 'UIDevToolsActivePort'):
            (self.profile / name).unlink(missing_ok=True)
        log = open(self.log_path, 'a')
        command, pass_fds = [str(self.binary)], ()
        if self.pipe:
            # The browser reads commands from fd 3 and writes replies to fd 4.
            to_browser, self.pipe_writer = os.pipe()
            self.pipe_reader, from_browser = os.pipe()
            pass_fds = (to_browser, from_browser)
            # bash: dash rejects descriptors above 9 in redirections.
            command = ['bash', '-c', f'exec "$0" "$@" 3<&{to_browser} 4>&{from_browser}',
                       str(self.binary), '--remote-debugging-pipe']
            self.pipe_next_id, self.pipe_buffer = 0, b''
        self.proc = subprocess.Popen(
            [*command, f'--ozone-platform={"wayland" if self.labwc else "x11"}',
             f'--user-data-dir={self.profile}',
             '--remote-debugging-port=0', '--enable-ui-devtools=0', '--lang=en-US',
             '--password-store=basic', '--enable-logging=stderr',
             f'--window-size={WINDOW[0]},{WINDOW[1]}', '--window-position=0,0', *self.args],
            env=self.env(), stdout=log, stderr=subprocess.STDOUT, pass_fds=pass_fds,
            preexec_fn=die_with_harness)
        log.close()
        for fd in pass_fds:
            os.close(fd)
        self.port = int(wait_for(lambda: self._read_port('DevToolsActivePort'), timeout=60,
                                 what='DevToolsActivePort'))
        self.ui_port = int(wait_for(lambda: self._read_port('UIDevToolsActivePort'),
                                    timeout=60, what='UIDevToolsActivePort'))
        wait_for(lambda: any(t['type'] == 'page' for t in self.targets()), what='a first tab')
        if self.labwc:
            # A Wayland client doesn't know where its window is; maximized, it
            # is at the output's origin, which is the Xvfb screen's.
            page = next(t for t in self.targets() if t['type'] == 'page')
            window = self.browser_call('Browser.getWindowForTarget', targetId=page['id'])
            self.browser_call('Browser.setWindowBounds', windowId=window['windowId'],
                              bounds={'windowState': 'maximized'})
            time.sleep(1)
        self._wait_ubo()

    def follow_relaunch(self):
        """After the browser relaunched itself (Settings' Restart button):
        waits for the old process to exit and talks to the new one, which
        isn't our child. It keeps the old command line and log."""
        # The new process rewrites the port files, maybe with the same ports.
        names = ('DevToolsActivePort', 'UIDevToolsActivePort')
        old = {name: (self.profile / name).exists() and (self.profile / name).stat().st_mtime_ns
               for name in names}
        self.proc.wait(timeout=60)
        self.proc = wait_for(lambda: Relaunched.find(self.profile), timeout=60,
                             what='the relaunched browser')

        def rewritten(name):
            path = self.profile / name
            return (path.exists() and path.stat().st_mtime_ns != old[name]
                    and self._read_port(name))

        self.port = int(wait_for(lambda: rewritten(names[0]), timeout=60,
                                 what=f'a new {names[0]}'))
        self.ui_port = int(wait_for(lambda: rewritten(names[1]), timeout=60,
                                    what=f'a new {names[1]}'))
        wait_for(lambda: any(t['type'] == 'page' for t in self.targets()), what='a first tab')
        self._wait_ubo()

    def _wait_ubo(self):
        """A page loaded before the bundled uBlock Origin listens isn't
        filtered (#201), and uBlock restarts on its first launch (#281), so a
        start waits until it filters. A profile that disables it
        (`disable_reasons` in its Preferences)
        doesn't wait."""
        for name in ('Preferences', 'Secure Preferences'):
            path = self.profile / 'Default' / name
            settings = json.loads(path.read_text()) if path.exists() else {}
            if settings.get('extensions', {}).get('settings', {}).get(UBO, {}).get('disable_reasons'):
                return
        self.ubo_background().close()

    def _read_port(self, name):
        path = self.profile / name
        if self.proc.poll() is not None:
            raise AssertionError(f'browser exited with {self.proc.returncode}; see {self.log_path}')
        text = path.read_text().split() if path.exists() else []
        return text[0] if text else None

    def quit(self):
        """Closes the browser the way a user would, so it saves its session."""
        if self.proc.poll() is None:
            try:
                session = Session(self._browser_ws())
                session.call('Browser.close')
            except (OSError, RuntimeError, ConnectionError):
                self.proc.terminate()
            self.proc.wait(timeout=30)

    def stop(self, failed=False):
        BROWSERS.discard(self)
        # With it, a relaunched browser nobody followed, and crashpad handlers,
        # in process groups of their own: whatever has this root on its command line.
        own = [self.proc] if self.proc else []
        end(*own, *(proc for proc in processes(str(self.root))
                    if proc.pid not in {p.pid for p in own}))
        if self.labwc:
            self.labwc.stop()
        self.xvfb.stop()
        if failed or KEEP:
            print(f'\n  kept {self.root} (log: {self.log_path})')
        else:
            shutil.rmtree(self.root, ignore_errors=True)

    # Chrome DevTools.

    def _get(self, path, method='GET'):
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
        return json.loads(body) if body.startswith((b'{', b'[')) else body

    def _browser_ws(self):
        return self._get('/json/version')['webSocketDebuggerUrl']

    def targets(self):
        return self._get('/json/list')

    def page(self, url_part, timeout=15):
        """Attaches to the first target whose URL contains `url_part`."""
        target = wait_for(lambda: next((t for t in self.targets() if url_part in t['url']), None),
                          timeout=timeout, what=f'a target with {url_part!r}')
        return Page(target)

    def new_tab(self, url):
        target = self._get('/json/new?' + url, method='PUT')
        self._get(f'/json/activate/{target["id"]}')
        return Page(target)

    def close_target(self, page):
        self._get(f'/json/close/{page.id}')
        wait_for(lambda: all(t['id'] != page.id for t in self.targets()), what='the tab to close')

    def browser_call(self, method, **params):
        session = Session(self._browser_ws())
        try:
            return session.call(method, **params)
        finally:
            session.close()

    def pipe_call(self, method, **params):
        """A browser-target command over the debugging pipe (Browser(pipe=True))."""
        self.pipe_next_id += 1
        os.write(self.pipe_writer, json.dumps({'id': self.pipe_next_id, 'method': method,
                                               'params': params}).encode() + b'\0')
        while True:
            while b'\0' not in self.pipe_buffer:
                if not select.select([self.pipe_reader], [], [], 60)[0]:
                    raise AssertionError(f'timed out after 60s waiting for {method}')
                chunk = os.read(self.pipe_reader, 65536)
                if not chunk:
                    raise ConnectionError('debugging pipe closed')
                self.pipe_buffer += chunk
            message, self.pipe_buffer = self.pipe_buffer.split(b'\0', 1)
            message = json.loads(message)
            if message.get('id') == self.pipe_next_id:
                if 'error' in message:
                    raise RuntimeError(f'{method}: {message["error"]}')
                return message.get('result', {})

    # UI DevTools.

    def views(self, cls, **props):
        """Views of class `cls` whose properties equal `props` (as strings)."""
        session = self._ui_session()
        try:
            root = session.call('DOM.getDocument')['root']
            nodes = []

            def walk(node, widget):
                attrs = node.get('attributes', [])
                if node.get('nodeName') == 'Widget':
                    widget = node['nodeId']
                if 'class' in attrs and attrs[attrs.index('class') + 1] == cls:
                    nodes.append((node['nodeId'], widget))
                for child in node.get('children', []):
                    walk(child, widget)

            walk(root, None)
            found = []
            for node, widget in nodes:
                try:
                    styles = session.call('CSS.getMatchedStylesForNode', nodeId=node)
                    values = {p['name']: p['value']
                              for rule in styles.get('matchedCSSRules', [])
                              for p in rule['rule']['style']['cssProperties']}
                    if all(values.get(k) == v for k, v in props.items()):
                        bounds = session.call('DOM.getNodeBoundsInScreen',
                                              nodeId=node)['boundsInScreen']
                        found.append(View(cls, values, bounds, widget))
                except RuntimeError as error:
                    # A view removed since DOM.getDocument (the toolbar
                    # changes as a download starts) isn't there any more.
                    if 'not found' not in str(error):
                        raise
            return found
        finally:
            session.close()

    def _ui_session(self):
        """A new UI DevTools connection. The server takes one client at a
        time, and leaves an upgrade unanswered while it hasn't seen the last
        one close yet (a poll reconnects right away), so that is tried again."""
        deadline = time.monotonic() + 30
        while True:
            try:
                return Session(f'ws://127.0.0.1:{self.ui_port}/0', handshake_timeout=3)
            except (OSError, ConnectionError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)

    def wait_view(self, cls, timeout=15, match=None, **props):
        """Waits for a visible view of class `cls` with `props` (and for which
        `match(view)` holds) to stop moving, and returns it. Toolbar buttons
        and dialogs animate into place, and a click must land on the button.
        """
        last = {}

        def settled():
            view = next((v for v in self.views(cls, **props)
                         if v.visible and (match is None or match(v))), None)
            previous, last['bounds'] = last.get('bounds'), view and view.bounds
            return view if view and view.bounds == previous else None

        return wait_for(settled, timeout=timeout, what=f'a visible {cls} with {props}')

    def menus(self):
        """Open menus, in the order they opened. Each is a list of its item
        groups (split at separators), each group a list of MenuItemViews, top
        to bottom. An item's `Title` is its label as in the menu model, with
        `&&` for an ampersand and `&` before a mnemonic.
        """
        widgets = {}
        for view in self.views('MenuItemView'):
            if view.visible:
                widgets.setdefault(view.widget, []).append(view)
        menus = []
        # Widget node ids grow as widgets are created.
        for widget in sorted(widgets):
            items = sorted(widgets[widget], key=lambda v: v.bounds['y'])
            groups = [[items[0]]]
            for above, item in zip(items, items[1:]):
                if item.bounds['y'] > above.bounds['y'] + above.bounds['height']:
                    groups.append([])
                groups[-1].append(item)
            menus.append(groups)
        return menus

    def ubo_background(self, extension_id=UBO):
        """uBlock Origin's background page once it filters. Seeing Chromium,
        uBlock restarts itself on its first launch, before it filters (#165):
        the target keeps its URL while its first page goes away, and an eval
        landing in between fails, so each try attaches anew."""
        url = f'chrome-extension://{extension_id}/background.html'

        def ready():
            page = None
            try:
                # The listed target can be the page that just went away.
                page = self.page(url, timeout=60)
                if page.eval('self.µBlock?.readyToFilter'):
                    return page
            except (OSError, RuntimeError, ConnectionError):
                pass
            if page:
                page.close()
        return wait_for(ready, timeout=60, what="uBlock Origin's background page")

    def wait_ubo_menu(self):
        """Waits for uBlock Origin's "Block element" context menu item, which
        it adds once it has set up the active tab's page, after the page loads.
        """
        ubo = self.page(f'chrome-extension://{UBO}/background.html')
        # An update of the item succeeds once the browser has it: the browser
        # handles the extension's menu calls in order.
        exists = ("new Promise(r => chrome.contextMenus.update('uBlock0-blockElement', {},"
                  " () => r(!chrome.runtime.lastError)))")
        try:
            wait_for(lambda: ubo.eval(exists), what='uBlock Origin\'s "Block element"')
        finally:
            ubo.close()

    # X11 input.

    def xdotool(self, *args):
        subprocess.run(['xdotool', *args], env=self.env(), check=True)

    def click_view(self, view, button=1):
        x, y = view.center
        self.xdotool('mousemove', str(x), str(y), 'click', str(button))

    def click_element(self, page, selector, button=1, repeat=1):
        """A real click (`repeat` 2: a double click) on an element of the
        active tab."""
        contents = self.wait_view('ContentsWebView')
        x, y = page.eval(f'(() => {{ const r = document.querySelector({json.dumps(selector)})'
                         '.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()')
        self.xdotool('mousemove', str(contents.bounds['x'] + int(x)),
                     str(contents.bounds['y'] + int(y)), 'click', '--repeat', str(repeat),
                     str(button))

    def key(self, *keys):
        """Keystrokes to the browser window. There is no window manager, so
        the window gets the input focus first."""
        if self.labwc:
            # labwc's output, the screen's only (and unnamed) window.
            found = subprocess.run(['xwininfo', '-root', '-children'], env=self.env(),
                                   capture_output=True, text=True, check=True)
            window = re.findall(r'^\s+(0x[0-9a-f]+) ', found.stdout, re.M)[0]
        else:
            # xdotool exits on a window that closes while it searches (a
            # menu, a tooltip), finding nothing: it tries again.
            window = wait_for(lambda: next(iter(subprocess.run(
                ['xdotool', 'search', '--onlyvisible', '--name', ' - oganesson$'],
                env=self.env(), capture_output=True, text=True, check=False).stdout.split()), None),
                what='the browser window')
        self.xdotool('windowfocus', '--sync', window)
        self.xdotool('key', *keys)

    # Health.

    def alive(self):
        return self.proc.poll() is None

    def new_fatal_lines(self):
        """FATAL/(D)CHECK lines logged since the previous call."""
        with open(self.log_path, errors='replace') as log:
            log.seek(self.log_offset)
            text = log.read()
            self.log_offset = log.tell()
        return [line for line in text.splitlines() if any(m in line for m in FATAL_MARKERS)]


class Relaunched:
    """A process that isn't our child (a relaunched browser), with the Popen
    calls the harness uses."""

    def __init__(self, pid):
        self.pid, self.returncode = pid, None

    @staticmethod
    def find(profile):
        """The browser process (no --type) running on `profile`, if any."""
        for entry in Path('/proc').iterdir():
            try:
                args = (entry / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
                # The release build's relaunched browser has a single argument
                # there, its command line joined with spaces.
                if len(args) == 1:
                    args = args[0].split(b' ')
            except (OSError, ValueError):
                continue
            if (f'--user-data-dir={profile}'.encode() in args
                    and not any(a.startswith(b'--type=') for a in args)):
                return Relaunched(int(entry.name))
        return None

    def poll(self):
        if self.returncode is None:
            try:
                state = Path(f'/proc/{self.pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
            except OSError:
                state = 'X'
            if state in ('Z', 'X'):
                self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        try:
            wait_for(lambda: self.poll() is not None, timeout=3600 if timeout is None else timeout,
                     what=f'process {self.pid} to exit')
        except AssertionError:
            raise subprocess.TimeoutExpired(str(self.pid), timeout)
        return self.returncode

    def terminate(self):
        self._signal(15)

    def kill(self):
        self._signal(9)

    def _signal(self, number):
        try:
            os.kill(self.pid, number)
        except ProcessLookupError:
            pass


class Server:
    """A local HTTP server. `routes` maps a path to (status, headers, body), or
    to a function of the request's headers that returns them. With `tls`, a
    (certificate, key) pair of files, it speaks HTTPS; with `ipv6`, it listens
    on ::1 instead of 127.0.0.1. `requests` lists the paths it was asked for, in order; `headers` maps a
    path to the headers of its last request, and `bodies` to the body of its
    last POST."""

    def __init__(self, routes, tls=None, ipv6=False):
        self.routes = routes
        self.scheme = 'https' if tls else 'http'
        self.requests = []
        self.headers = {}
        self.bodies = {}
        routes_ref, requests_ref, headers_ref = self.routes, self.requests, self.headers
        bodies_ref = self.bodies

        class Handler(http.server.BaseHTTPRequestHandler):

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                bodies_ref[urllib.parse.urlparse(self.path).path] = body
                self.do_GET()

            def do_GET(self):
                requests_ref.append(urllib.parse.urlparse(self.path).path)
                headers_ref[requests_ref[-1]] = dict(self.headers)
                route = routes_ref.get(urllib.parse.urlparse(self.path).path)
                if callable(route):
                    route = route(self.headers)
                status, headers, body = route if route else (404, {}, b'not found')
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer
        if ipv6:
            server = type('Server', (server,), {'address_family': socket.AF_INET6})
        self.httpd = server(('::1' if ipv6 else '127.0.0.1', 0), Handler)
        self.port = self.httpd.server_address[1]
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(*tls)
            self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path, host='127.0.0.1'):
        return f'{self.scheme}://{host}:{self.port}{path}'

    def stop(self):
        self.httpd.shutdown()


class BrowserTest(unittest.TestCase):
    """One browser per test class. Every test also checks that it didn't crash."""

    browser_args = ()
    first_run = False
    prefs = None
    browser_env = None
    debugging_pipe = False
    wayland = WAYLAND

    @classmethod
    def setUpClass(cls):
        cls.browser = Browser(cls.browser_args, first_run=cls.first_run, prefs=cls.prefs,
                              env=cls.browser_env, pipe=cls.debugging_pipe,
                              wayland=cls.wayland)
        cls.failed = False

    @classmethod
    def tearDownClass(cls):
        cls.browser.stop(failed=cls.failed)

    def run(self, result=None):
        result = result or self.defaultTestResult()
        before = len(result.failures) + len(result.errors)
        super().run(result)
        if len(result.failures) + len(result.errors) > before:
            type(self).failed = True
            # The screen at the failure, kept with the log (ImageMagick's
            # import, if installed).
            if shutil.which('import'):
                subprocess.run(['import', '-window', 'root',
                                str(self.browser.root / f'{self._testMethodName}.png')],
                               env=self.browser.env(), check=False)
        return result

    def tearDown(self):
        fatal = self.browser.new_fatal_lines()
        self.assertEqual(fatal, [], 'the browser logged a crash or a failed check')
        self.assertTrue(self.browser.alive(), 'the browser exited')
