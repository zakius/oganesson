"""Installed web apps' out-of-scope links open in the system default browser,
with the scope rules the user adds on chrome://app-settings and the start
address set there, and from a link's context menu in an app window; also for
DIY apps, and not for isolated web apps. In normal tabs, "Open in app" and link capturing follow the scope
rules too. A stub `xdg-open` on PATH stands in for the desktop's default
handler and records the URLs it gets, and the activation token variables it
sees, which decide whether the browser it starts may take focus; a stub `xdg-settings` and a desktop
file make oganesson the default browser when a test needs it. An app window
also stays usable while a regular window shows a "Leave this page?" dialog.
"""

import base64
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from harness import BrowserTest, Page, Server, wait_for


APP_PAGE = b'''<!doctype html><link rel="manifest" href="/app/manifest.json">
<a id="plain" href="/out.html?plain">out</a>
<a id="blank" href="/out.html?blank" target="_blank">out in a new tab</a>
<a id="inside" href="/app/inside.html">in scope</a>
<form method="post" action="/post.html" target="_blank"><input name="q" value="1">
<button id="post">post</button></form>
<form method="post" action="/post-opener.html" target="_blank" rel="opener"><input name="q" value="2">
<button id="post-opener">post with opener</button></form>
<button id="sign-in" onclick="(async () => { await fetch('/app/inside.html');
  location.assign('/out.html?assign'); })()">sign in</button>
<a id="cross-in" href="/other/in.html">another origin, in a user rule</a>
<a id="cross-out" href="/elsewhere.html">another origin, in no rule</a>
<a id="excluded" href="/app/excluded.html">excluded by a user rule</a>
<a id="mail" href="/app/mail/x.html">in a rule on the app's own site</a>
<a id="push" href="/app/excluded.html" onclick="event.preventDefault();
  history.pushState(null, '', this.href)">excluded, pushed</a>
<a id="replace" href="/app/excluded.html" onclick="event.preventDefault();
  history.replaceState(null, '', this.href)">excluded, replaced</a>
<a id="push-out" href="/out.html?push" onclick="event.preventDefault();
  window.sawClick = true; history.pushState(null, '', this.href)">out of scope, pushed</a>
<a id="push-inside" href="/app/inside.html" onclick="event.preventDefault();
  history.pushState(null, '', this.href)">in scope, pushed</a>
<a id="assign" href="/app/excluded.html" onclick="event.preventDefault();
  location.href = this.href">excluded, by script</a>
<a id="rewrite" href="/app/inside.html"
  onmousedown="this.href = '/app/to-excluded'">excluded, through a redirect</a>
<a id="rewrite-out" href="/app/inside.html"
  onmousedown="this.href = '/app/to-out'">out of scope, through a redirect</a>
<p><button id="replace-button" onclick="history.replaceState(null, '', '/app/excluded.html')">
excluded, replaced by a button</button>
<button id="assign-button" onclick="location.href = '/app/excluded.html'">
excluded, by a button's script</button>
<button id="push-twice" onclick="history.pushState(null, '', '/out.html?first');
  history.pushState(null, '', '/out.html?second')">out of scope, pushed twice</button></p>
<script>window.popstates = 0;
addEventListener('popstate', () => window.popstates++);
for (const id of ['cross-in', 'cross-out'])
  document.getElementById(id).host = `localhost:${location.port}`;</script>'''

# Rules for the app: localhost's /other/ joins its scope, and one page of its
# manifest scope leaves it.
RULES = 'http://localhost:*/other/*\n!http://127.0.0.1:*/app/excluded.html'
# A rule on the app's own site, which narrows its scope there to /app/mail/.
NARROW = 'http://127.0.0.1:*/app/mail/*'
# A page out of the app, for a normal tab: links an app can capture.
LINKS_PAGE = b'''<!doctype html>
<a id="mail" href="/app/mail/x.html" target="_blank">in a narrowing rule</a>
<a id="inside" href="/app/inside.html" target="_blank">in the manifest scope</a>
<a id="excluded" href="/app/excluded.html" target="_blank">excluded</a>'''
# The address bar's "Open in app" icon: its tooltip with and without the
# link capturing UX.
OPEN_IN_APP = {'Open in app', 'To open this link, choose an app'}



def png(size):
    """A blank square PNG: install wants a manifest icon of at least 144px."""
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))
    rows = b''.join(b'\0' + b'\x80' * size * 3 for _ in range(size))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def app_id_of(manifest_id):
    """GenerateAppIdFromManifestId: a crx-style ID of the manifest ID's hash."""
    return hashlib.sha256(hashlib.sha256(manifest_id.encode()).digest()).hexdigest()[:32].translate(
        str.maketrans('0123456789abcdef', 'abcdefghijklmnop'))


def install_app(browser, manifest_id, url):
    """Installs the app at `url` and sets it to open in its own window."""
    browser.pipe_call('PWA.install', manifestId=manifest_id, installUrlOrBundleUrl=url)
    # Installed this way, an app opens in a tab until set to its own window.
    browser.pipe_call('PWA.changeAppUserSettings', manifestId=manifest_id,
                      displayMode='standalone')


class WebAppTest(BrowserTest):
    """The app installed and the stubs on PATH; tests in the classes below."""

    debugging_pipe = True
    # The host the app is installed from, and members to add to its manifest.
    app_host = '127.0.0.1'
    manifest_extra = {}
    # The app's start page, and its manifest ID's path.
    app_page = APP_PAGE
    manifest_path = '/app/'

    @classmethod
    def setUpClass(cls):
        cls.stubs = Path(tempfile.mkdtemp(prefix='oganesson-e2e-stubs-'))
        cls.opened_file = cls.stubs / 'opened'
        cls.tokens_file = cls.stubs / 'tokens'
        cls.is_default_file = cls.stubs / 'is-default'
        cls.desktop_file = cls.stubs / 'data/applications/oganesson.desktop'
        cls.handler_file = cls.stubs / 'https-handler'
        cls.other_desktop_file = cls.stubs / 'data/applications/other.desktop'
        (cls.stubs / 'bin').mkdir()
        for name, body in (
                # The token variables first: tests wait for the URL.
                ('xdg-open', 'printf "%s\\n" "$(env | grep -oE'
                             ' "^(XDG_ACTIVATION_TOKEN|DESKTOP_STARTUP_ID)=" | tr -d =)"'
                             f' >> {cls.tokens_file}\n'
                             f'printf "%s\\n" "$1" >> {cls.opened_file}\n'),
                # Chromium asks `xdg-settings check default-web-browser
                # oganesson.desktop`, and `xdg-settings get
                # default-url-scheme-handler https` for the handler's name.
                ('xdg-settings', f'if [ "$1" = get ]; then cat {cls.handler_file} 2>/dev/null\n'
                                 f'elif [ -e {cls.is_default_file} ]; then echo yes; else echo no; fi\n')):
            (cls.stubs / 'bin' / name).write_text('#!/bin/sh\n' + body)
            (cls.stubs / 'bin' / name).chmod(0o755)
        cls.browser_env = {'PATH': f'{cls.stubs / "bin"}:{os.environ["PATH"]}',
                           'XDG_DATA_HOME': str(cls.stubs / 'data')}
        super().setUpClass()
        cls.server = Server(routes={
            '/app/index.html': (200, {'Content-Type': 'text/html'}, cls.app_page),
            '/app/inside.html': (200, {'Content-Type': 'text/html'}, b'inside'),
            '/app/popup.html': (200, {'Content-Type': 'text/html'},
                                b'<a id="out" href="/out.html?popup">out</a>'),
            '/out.html': (200, {'Content-Type': 'text/html'}, b'out'),
            '/other/in.html': (200, {'Content-Type': 'text/html'}, b'other'),
            '/elsewhere.html': (200, {'Content-Type': 'text/html'}, b'elsewhere'),
            '/app/excluded.html': (200, {'Content-Type': 'text/html'}, b'excluded'),
            '/app/mail/x.html': (200, {'Content-Type': 'text/html'}, b'mail'),
            '/app/start.html': (200, {'Content-Type': 'text/html'}, b'start'),
            '/links.html': (200, {'Content-Type': 'text/html'}, LINKS_PAGE),
            '/post.html': (200, {'Content-Type': 'text/html'}, b'posted'),
            '/post-opener.html': (200, {'Content-Type': 'text/html'}, b'posted'),
            '/app/icon.png': (200, {'Content-Type': 'image/png'}, png(192)),
            '/app/manifest.json': (200, {'Content-Type': 'application/manifest+json'}, json.dumps({
                'name': 'Links', 'id': '/app/', 'start_url': '/app/index.html',
                'scope': '/app/', 'display': 'standalone',
                'icons': [{'src': 'icon.png', 'sizes': '192x192', 'type': 'image/png'}],
                **cls.manifest_extra}).encode()),
        })
        # Out of the app's scope, and redirects into it.
        # In the app's scope, and redirect out of it: to an excluded page, and
        # to a page in no rule.
        cls.server.routes['/app/to-excluded'] = (302, {'Location': '/app/excluded.html'}, b'')
        cls.server.routes['/app/to-out'] = (302, {'Location': '/out.html?redirect'}, b'')
        cls.server.routes['/bounce'] = (302, {'Location': cls.server.url('/app/start.html', cls.app_host)}, b'')
        cls.manifest_id = cls.server.url(cls.manifest_path, cls.app_host)
        cls.install()
        cls.app_id = app_id_of(cls.manifest_id)

    @classmethod
    def install(cls):
        install_app(cls.browser, cls.manifest_id, cls.server.url('/app/index.html', cls.app_host))

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        super().tearDownClass()
        shutil.rmtree(cls.stubs, ignore_errors=True)

    def setUp(self):
        self.opened_file.unlink(missing_ok=True)
        self.tokens_file.unlink(missing_ok=True)
        self.is_default_file.unlink(missing_ok=True)
        self.desktop_file.unlink(missing_ok=True)
        self.handler_file.unlink(missing_ok=True)

    def launch_app(self, close=True, url=None, launch=None):
        """Launches the app with PWA.launch, or with `launch()`, and returns
        its window's page once on screen; it must open at `url`."""
        # PWA.launch's targetId isn't the window's page target: take the new one.
        before = {t['id'] for t in self.browser.targets()}
        if launch:
            launch()
        else:
            self.browser.pipe_call('PWA.launch', manifestId=self.manifest_id)
        start = url or self.server.url('/app/index.html', self.app_host)
        target = wait_for(lambda: next((t for t in self.browser.targets() if t['id'] not in before
                                        and t['url'] == start), None),
                          what='the app window')
        app = Page(target)
        if close:
            self.addCleanup(self.browser.close_target, app)
        # An eval while the page is still provisional fails a DCHECK in its
        # renderer (crbug.com/897816); the browser knows once it commits. A
        # target that has only just appeared may not have its page attached yet.
        def committed():
            try:
                history = app.call('Page.getNavigationHistory')
            except RuntimeError as error:
                if 'Not attached to an active page' in str(error):
                    return False
                raise
            return history['entries'][history['currentIndex']]['url'] == start

        wait_for(committed, what='the start page committed')
        if url:
            wait_for(lambda: app.eval('document.readyState === "complete"'), what='the start page')
            return app
        self.wait_on_screen(app)
        return app

    @staticmethod
    def wait_on_screen(app):
        # The first app window shows a while after its page loads; a click
        # before its first frame misses the link. Without a gesture, which
        # would leave the page user activation for its next few seconds.
        wait_for(lambda: app.eval('!!document.getElementById("plain") && innerWidth > 0'
                                  ' && document.visibilityState === "visible"', gesture=False),
                 what='the app page on screen')
        app.eval('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))',
                 gesture=False)

    def opened(self):
        return self.opened_file.read_text().splitlines() if self.opened_file.exists() else []

    def out_tabs(self, path='/out.html'):
        return [t['url'] for t in self.browser.targets() if path in t['url']]

    def link_menu(self, app, selector):
        """Right-clicks the link `selector` in the app window; returns the
        context menu's first item group, its "Open link in" items."""
        app.click(selector, button='right')
        return wait_for(lambda: self.browser.menus(), what='the context menu')[0][0]

    def close_menus(self):
        # The open menu has the keyboard grab.
        self.browser.xdotool('key', 'Escape')
        wait_for(lambda: not self.browser.menus(), what='the menu to close')

    def set_default_browser_name(self, name):
        """Makes the default https handler a desktop entry named `name`."""
        self.other_desktop_file.parent.mkdir(parents=True, exist_ok=True)
        self.other_desktop_file.write_text(f'[Desktop Entry]\nType=Application\nName={name}\n')
        self.handler_file.write_text('other.desktop\n')

    def wait_link_menu_titles(self, app, selector, titles):
        """Right-clicks the link `selector` and waits, in that one menu, for
        the default browser items' titles to be `titles`."""
        app.click(selector, button='right')
        try:
            wait_for(lambda: [v['Title'] for v in (self.browser.menus() or [[[]]])[0][0][1:3]] == titles,
                     what=f'the menu items {titles}')
        finally:
            self.close_menus()

    def make_default_browser(self):
        self.desktop_file.parent.mkdir(parents=True, exist_ok=True)
        self.desktop_file.write_text('[Desktop Entry]\nType=Application\nName=oganesson\n')
        self.is_default_file.touch()

    def settings_rules(self, rules=None, layout=False):
        """Opens the app's settings page; with `rules`, saves them there.
        Returns the rules the page shows, its error message, and whether that
        message is on screen; with `layout`, then the rules row's content box
        and the textarea, its error message and the Save button's boxes."""
        tab = self.browser.new_tab(f'chrome://app-settings/{self.app_id}')
        try:
            item = ('document.querySelector("web-app-settings-app")?.shadowRoot?'
                    '.querySelector("app-management-scope-rules-item")')
            # The tab shows about:blank first, then the page before its
            # elements upgrade, then the app, then the app's rules. Asked after
            # the item's own request, on the same pipe, the backend answers
            # after it too.
            wait_for(lambda: tab.eval(
                f'(async () => {{ const item = {item};'
                f' if (item?.app?.id !== {json.dumps(self.app_id)}) return false;'
                ' await item.updateComplete;'
                ' const {browserProxyFactory} = await import("chrome://resources/'
                'cr_components/app_management/app_management.mojom-webui.js");'
                ' const {rules} = await browserProxyFactory.getInstance().handler'
                f'.getScopeRules({json.dumps(self.app_id)});'
                ' await item.updateComplete;'
                ' return item.shadowRoot.querySelector("#rules").value === rules; })()'),
                     what='the scope rules on the settings page')
            if rules is not None:
                tab.eval(f'(async () => {{ const item = {item};'
                         ' const textarea = item.shadowRoot.querySelector("#rules");'
                         f' textarea.value = {json.dumps(rules)};'
                         ' await textarea.updateComplete; await item.updateComplete;'
                         ' item.shadowRoot.querySelector("#save").click(); })()')
                wait_for(lambda: tab.eval(f'{item}.shadowRoot.querySelector("#save")'
                                          '.textContent.trim() === "Saved"'
                                          f' || !!{item}.shadowRoot.querySelector("#rules").firstFooter'),
                         what='the rules saved or rejected')
            return tab.eval(f'(async () => {{ const rules = {item}.shadowRoot.querySelector("#rules");'
                            ' await rules.updateComplete;'
                            ' const footer = rules.shadowRoot.querySelector("#firstFooter");'
                            ' const box = e => { const r = e.getBoundingClientRect();'
                            ' return {left: r.left, right: r.right, top: r.top, bottom: r.bottom}; };'
                            f' const card = {item}; const style = getComputedStyle(card);'
                            ' const content = box(card);'
                            ' content.left += parseFloat(style.paddingLeft);'
                            ' content.right -= parseFloat(style.paddingRight);'
                            ' return [rules.value, rules.firstFooter,'
                            ' footer.checkVisibility() && footer.offsetHeight > 0,'
                            f' ...({json.dumps(layout)} ? [{{card: content, textarea: box(rules.shadowRoot.querySelector("#input")),'
                            ' error: box(footer), save: box(card.shadowRoot.querySelector("#save"))}] : [])]; })()')
        finally:
            self.browser.close_target(tab)

    def set_rules(self, rules):
        self.assertEqual(self.settings_rules(rules), [rules, '', False])
        self.addCleanup(self.settings_rules, '')

    def settings_strict(self, click=False):
        """Opens the app's settings page; with `click`, toggles the strict
        scope checkbox and saves. Returns whether the box is checked, then
        whether the backend has the scope strict."""
        tab = self.browser.new_tab(f'chrome://app-settings/{self.app_id}')
        try:
            item = ('document.querySelector("web-app-settings-app")?.shadowRoot?'
                    '.querySelector("app-management-scope-rules-item")')
            handler = ('(await import("chrome://resources/cr_components/app_management/'
                       'app_management.mojom-webui.js")).browserProxyFactory.getInstance().handler')
            # As in settings_rules: asked after the item's own request.
            wait_for(lambda: tab.eval(
                f'(async () => {{ const item = {item};'
                f' if (item?.app?.id !== {json.dumps(self.app_id)}) return false;'
                f' const {{strict}} = await {handler}.getScopeRules({json.dumps(self.app_id)});'
                ' await item.updateComplete;'
                ' return item.shadowRoot.querySelector("#strict").checked === strict; })()'),
                     what='the strict scope box on the settings page')
            if click:
                tab.eval(f'(async () => {{ const item = {item};'
                         ' item.shadowRoot.querySelector("#strict").click();'
                         ' await item.updateComplete;'
                         ' item.shadowRoot.querySelector("#save").click(); })()')
                wait_for(lambda: tab.eval(f'{item}.shadowRoot.querySelector("#save")'
                                          '.textContent.trim() === "Saved"'),
                         what='the strict scope saved')
            return tab.eval(f'(async () => [{item}.shadowRoot.querySelector("#strict").checked,'
                            f' (await {handler}.getScopeRules({json.dumps(self.app_id)})).strict])()')
        finally:
            self.browser.close_target(tab)

    def set_strict(self):
        self.assertEqual(self.settings_strict(click=True), [True, True])
        self.addCleanup(self.settings_strict, True)

    def settings_start_url(self, url=None):
        """Opens the app's settings page; with `url`, saves it as the start
        address there. Returns the address the page shows, its placeholder
        and its error message."""
        tab = self.browser.new_tab(f'chrome://app-settings/{self.app_id}')
        try:
            item = ('document.querySelector("web-app-settings-app")?.shadowRoot?'
                    '.querySelector("app-management-start-url-item")')
            # As in settings_rules: asked after the item's own request.
            wait_for(lambda: tab.eval(
                f'(async () => {{ const item = {item};'
                f' if (item?.app?.id !== {json.dumps(self.app_id)}) return false;'
                ' await item.updateComplete;'
                ' const {browserProxyFactory} = await import("chrome://resources/'
                'cr_components/app_management/app_management.mojom-webui.js");'
                ' const {url} = await browserProxyFactory.getInstance().handler'
                f'.getStartUrl({json.dumps(self.app_id)});'
                ' await item.updateComplete;'
                ' return item.shadowRoot.querySelector("#url").value === url; })()'),
                     what='the start address on the settings page')
            if url is not None:
                tab.eval(f'(async () => {{ const item = {item};'
                         ' const input = item.shadowRoot.querySelector("#url");'
                         f' input.value = {json.dumps(url)};'
                         ' await input.updateComplete; await item.updateComplete;'
                         ' item.shadowRoot.querySelector("#save").click(); })()')
                wait_for(lambda: tab.eval(f'{item}.shadowRoot.querySelector("#save")'
                                          '.textContent.trim() === "Saved"'
                                          f' || !!{item}.shadowRoot.querySelector("#url").errorMessage'),
                         what='the start address saved or rejected')
            return tab.eval(f'(async () => {{ const input = {item}.shadowRoot.querySelector("#url");'
                            ' await input.updateComplete;'
                            ' return [input.value, input.placeholder, input.errorMessage]; })()')
        finally:
            self.browser.close_target(tab)

    def set_start_url(self, url):
        self.assertEqual(self.settings_start_url(url),
                         [url, self.server.url('/app/index.html'), ''])
        self.addCleanup(self.settings_start_url, '')

    def custom_tab_bar_shown(self):
        return any(v.visible for v in self.browser.views('CustomTabBarView'))


class WebAppLinksTest(WebAppTest):

    def test_user_rule_keeps_link_in_app(self):
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#cross-in')
        wait_for(lambda: app.eval('location.href') == self.server.url('/other/in.html', 'localhost'),
                 what='the matched page in the app window')
        self.assertEqual(self.opened(), [])

    def test_user_rule_change_updates_open_window(self):
        # An app window on a page a rule brought into scope shows no
        # out-of-app bar; once the rule is gone, it does, without navigating.
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#cross-in')
        wait_for(lambda: app.eval('location.href') == self.server.url('/other/in.html', 'localhost'),
                 what='the matched page in the app window')
        self.assertFalse(self.custom_tab_bar_shown())
        self.assertEqual(self.settings_rules(''), ['', '', False])
        wait_for(self.custom_tab_bar_shown, what='the out-of-app bar')
        self.assertEqual(app.eval('location.href'), self.server.url('/other/in.html', 'localhost'))

    def test_user_rule_unmatched_link_opens_in_default_browser(self):
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#cross-out')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/elsewhere.html', 'localhost')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))

    def test_user_rule_excludes_manifest_scope(self):
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#excluded')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/excluded.html')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))

    def assert_excluded_opened(self, app, url='/app/index.html'):
        """The excluded page went to the default browser, and the app window
        is back at `url`."""
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/excluded.html')])
        wait_for(lambda: app.eval('location.href') == self.server.url(url),
                 what='the app window back')

    def test_excluded_push_from_link_handler_never_changes_address(self):
        # pushState asks the browser first: the address stays, no entry. From
        # a click handler that keeps the link in the page, as Facebook's does.
        self.set_rules(RULES)
        app = self.launch_app()
        length = app.eval('history.length')
        app.click('#push')
        self.assert_excluded_opened(app)
        self.assertEqual(app.eval('history.length'), length)

    def test_excluded_replace_never_changes_address(self):
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#replace-button')
        self.assert_excluded_opened(app)
        self.assertEqual(app.eval('history.length'), 1)

    def test_exclusion_takes_script_navigation_out(self):
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#assign-button')
        self.assert_excluded_opened(app)

    def test_exclusion_takes_script_navigation_without_gesture_out(self):
        self.set_rules(RULES)
        app = self.launch_app()
        app.eval('location.href = "/app/excluded.html"')
        self.assert_excluded_opened(app)

    def test_exclusion_takes_redirect_out(self):
        # A link whose href changes on mousedown to a redirector in scope.
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#rewrite')
        self.assert_excluded_opened(app)
        self.assertIn('/app/to-excluded', self.server.requests)

    def test_in_scope_push_stays_in_app(self):
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#push-inside')
        wait_for(lambda: app.eval('location.href') == self.server.url('/app/inside.html'),
                 what='the pushed page in the app window')
        self.assertEqual(self.opened(), [])

    def test_out_of_scope_push_from_link_handler_never_changes_address(self):
        # Facebook's links push their URL from a click handler: the handler
        # runs, its pushState doesn't.
        app = self.launch_app()
        length = app.eval('history.length')
        app.click('#push-out')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?push')])
        self.assertTrue(app.eval('window.sawClick', gesture=False))
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))
        self.assertEqual(app.eval('history.length'), length)

    def test_dropped_push_fires_popstate(self):
        # A router that drew the pushed page draws the current one again, as
        # after Back: Facebook's photo viewer closes.
        app = self.launch_app()
        app.click('#push-out')
        wait_for(lambda: app.eval('window.popstates', gesture=False) == 1,
                 what='a popstate after the dropped push')
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))

    def test_dropped_push_without_gesture_fires_no_popstate(self):
        self.set_strict()
        app = self.launch_app()
        app.eval('history.pushState(null, "", "/out.html?script")', gesture=False)
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(app.eval('window.popstates', gesture=False), 0)

    def test_out_of_scope_pushes_open_one_tab_per_input(self):
        # A router that answers with another URL, or tries again.
        app = self.launch_app()
        app.click('#push-twice')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?first')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))

    def test_out_of_scope_push_in_normal_tab_changes_address(self):
        # Tabs don't ask the browser.
        tab = self.browser.new_tab(self.server.url('/app/index.html'))
        self.addCleanup(self.browser.close_target, tab)
        # Not readyState: the new tab is complete on about:blank first.
        wait_for(lambda: tab.eval('location.href') == self.server.url('/app/index.html'),
                 what='the app page in a tab')
        tab.click('#push-out')
        wait_for(lambda: tab.eval('location.href', gesture=False) == self.server.url('/out.html?push'),
                 what='the pushed address in the tab')
        self.assertEqual(self.opened(), [])

    def test_out_of_scope_push_without_gesture_stays_in_app(self):
        app = self.launch_app()
        app.eval('history.pushState(null, "", "/out.html?script")', gesture=False)
        self.assertEqual(app.eval('location.href'), self.server.url('/out.html?script'))
        self.assertEqual(self.opened(), [])

    def push_after_click_in_other_window(self):
        """Clicks in one app window, then opens another, whose script pushes
        an out-of-scope URL; returns the new window. Since Chromium 158 a new
        app window has the user activation of a click in another window for
        its first 5 s, as the activation of script run in it (kWebScriptExec).
        That isn't input in the page, so the push isn't from a click."""
        other = self.launch_app()
        other.click('#push-inside')
        app = self.launch_app()
        # The activation reaches the new window's document shortly after it
        # loads, with the first script Chromium runs there.
        wait_for(lambda: app.eval('navigator.userActivation.isActive', gesture=False),
                 timeout=4, what='the click\'s activation in the new window')
        active = app.eval('[navigator.userActivation.isActive,'
                          ' history.pushState(null, "", "/out.html?script")][0]', gesture=False)
        self.assertTrue(active, 'the new window had no activation from the click')
        return app

    def test_out_of_scope_push_after_click_in_other_window_stays_in_app(self):
        app = self.push_after_click_in_other_window()
        self.assertEqual(app.eval('location.href', gesture=False),
                         self.server.url('/out.html?script'))
        # Nor does the browser send it out after the fact: the default
        # browser gets only the next click's link.
        app.click('#plain')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?plain')])

    def test_strict_push_after_click_in_other_window_fires_no_popstate(self):
        self.set_strict()
        app = self.push_after_click_in_other_window()
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?script')])
        self.assertEqual(app.eval('window.popstates', gesture=False), 0)

    def test_redirect_out_of_scope_stays_in_app(self):
        # Only exclusions follow redirects: sign-in flows go through them.
        self.set_rules(RULES)
        app = self.launch_app()
        app.click('#rewrite-out')
        wait_for(lambda: app.eval('location.href') == self.server.url('/out.html?redirect'),
                 what='the redirect target in the app window')
        self.assertEqual(self.opened(), [])

    def test_strict_redirect_out_of_scope_opens_in_default_browser(self):
        self.set_strict()
        app = self.launch_app()
        app.click('#rewrite-out')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?redirect')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))

    def test_strict_script_navigation_from_click_opens_in_default_browser(self):
        self.set_strict()
        app = self.launch_app()
        app.click('#sign-in')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?assign')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))

    def test_strict_push_without_gesture_never_changes_address(self):
        self.set_strict()
        app = self.launch_app()
        app.eval('history.pushState(null, "", "/out.html?script")', gesture=False)
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?script')])
        self.assertEqual(app.eval('location.href', gesture=False),
                         self.server.url('/app/index.html'))

    def test_strict_popup_opens_in_default_browser(self):
        self.set_strict()
        app = self.launch_app()
        app.eval('void window.open("/out.html?popup", "", "popup,width=400,height=300")')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?popup')])
        self.assertEqual(self.out_tabs(), [])

    def test_strict_in_scope_popup_stays(self):
        self.set_strict()
        app = self.launch_app()
        app.eval('void window.open("/app/popup.html", "", "popup,width=400,height=300")')
        popup = self.browser.page('/app/popup.html')
        self.addCleanup(self.browser.close_target, popup)
        self.assertEqual(self.opened(), [])

    def test_strict_off_by_default_and_persists(self):
        self.assertEqual(self.settings_strict(), [False, False])
        self.set_strict()
        self.browser.quit()
        prefs = json.loads((self.browser.profile / 'Default/Preferences').read_text())
        self.assertEqual(prefs['oganesson']['web_apps']['strict_scope'], {self.app_id: True})
        self.browser.start()
        self.assertEqual(self.settings_strict(), [True, True])

    def test_user_rule_on_app_site_narrows_scope(self):
        # the manifest's /app/ on 127.0.0.1 gives way to the rule there.
        self.set_rules(NARROW)
        app = self.launch_app()
        app.click('#inside')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/inside.html')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))

    def test_user_rule_on_app_site_keeps_its_pages(self):
        self.set_rules(NARROW)
        app = self.launch_app()
        app.click('#mail')
        wait_for(lambda: app.eval('location.href') == self.server.url('/app/mail/x.html'),
                 what='the matched page in the app window')
        self.assertEqual(self.opened(), [])

    def test_user_rule_elsewhere_adds_beside_narrowing(self):
        self.set_rules(f'{NARROW}\nhttp://localhost:*/other/*')
        app = self.launch_app()
        app.click('#cross-in')
        wait_for(lambda: app.eval('location.href') == self.server.url('/other/in.html', 'localhost'),
                 what='the matched page in the app window')
        self.assertEqual(self.opened(), [])

    def test_exclusion_wins_over_narrowing(self):
        self.set_rules(f'{NARROW}\n!http://127.0.0.1:*/app/mail/x.html')
        app = self.launch_app()
        app.click('#mail')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/mail/x.html')])

    def test_removing_narrowing_rule_restores_scope(self):
        # The start page is out of the narrowed scope, so the window shows the
        # out-of-app bar; without the rule, the whole /app/ is back in.
        self.set_rules(NARROW)
        app = self.launch_app()
        wait_for(self.custom_tab_bar_shown, what='the out-of-app bar')
        self.assertEqual(self.settings_rules(''), ['', '', False])
        wait_for(lambda: not self.custom_tab_bar_shown(), what='the out-of-app bar gone')
        app.click('#inside')
        wait_for(lambda: app.eval('location.href') == self.server.url('/app/inside.html'),
                 what='the in-scope page in the app window')
        self.assertEqual(self.opened(), [])

    def test_user_rule_invalid_rejected(self):
        self.set_rules(RULES)
        # URLPattern without regexp groups: SimpleUrlPatternMatcher's limit.
        rules, error, shown = self.settings_rules('http://localhost:*/other/*\nhttp://example.com/(\\d+)')
        self.assertTrue(error.startswith('Invalid pattern "http://example.com/(\\d+)": '), error)
        self.assertTrue(shown)
        self.assertEqual(self.settings_rules(), [RULES, '', False])

    def test_rules_row_stacks(self):
        # the textarea spans the row, the error and Save below it.
        *_, shown, boxes = self.settings_rules('http://example.com/(\\d+)', layout=True)
        self.assertTrue(shown)
        card, textarea, error, save = (boxes[k] for k in ('card', 'textarea', 'error', 'save'))
        self.assertGreaterEqual(textarea['right'] - textarea['left'], 0.8 * (card['right'] - card['left']))
        self.assertGreaterEqual(error['top'], textarea['bottom'])
        self.assertGreaterEqual(save['top'], error['bottom'])
        self.assertAlmostEqual(save['right'], card['right'], delta=1)

    def test_user_rules_persist_across_restart(self):
        self.set_rules(RULES)
        self.browser.quit()
        prefs = json.loads((self.browser.profile / 'Default/Preferences').read_text())
        self.assertEqual(prefs['oganesson']['web_apps']['user_scope_rules'],
                         {self.app_id: RULES.split('\n')})
        self.browser.start()
        self.assertEqual(self.settings_rules(), [RULES, '', False])
        app = self.launch_app()
        app.click('#cross-in')
        wait_for(lambda: app.eval('location.href') == self.server.url('/other/in.html', 'localhost'),
                 what='the matched page in the app window')
        self.assertEqual(self.opened(), [])

    def test_plain_link_opens_in_default_browser(self):
        app = self.launch_app()
        app.click('#plain')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?plain')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))
        self.assertEqual(self.out_tabs(), [])

    def test_blank_link_opens_in_default_browser(self):
        app = self.launch_app()
        app.click('#blank')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?blank')])
        self.assertEqual(self.out_tabs(), [])

    def test_window_open_opens_in_default_browser(self):
        app = self.launch_app()
        app.eval('void window.open("/out.html?open")')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?open')])
        self.assertEqual(self.out_tabs(), [])

    def test_handed_back_link_opens_in_tab(self):
        # oganesson as the default browser gets the app window's link from
        # xdg-open: a second process passes it on while the app window is the
        # last active one. It opens in a tab of the tabbed window.
        tabbed = next(t for t in self.browser.targets() if t['type'] == 'page')
        app = self.launch_app()
        url = self.server.url('/out.html?handed')
        subprocess.run([str(self.browser.binary), f'--user-data-dir={self.browser.profile}',
                        f'--ozone-platform={"wayland" if self.browser.labwc else "x11"}', url],
                       env=self.browser.env(), timeout=60, check=True)
        tab = self.browser.page('/out.html?handed')
        self.addCleanup(self.browser.close_target, tab)
        window = lambda t: self.browser.browser_call('Browser.getWindowForTarget',
                                                     targetId=t)['windowId']
        self.assertEqual(window(tab.id), window(tabbed['id']))
        self.assertNotEqual(window(tab.id), window(app.id))

    def test_popup_link_stays_in_popup(self):
        # A sign-in popup: its links stay in it, opener and all.
        app = self.launch_app()
        app.eval('void window.open("/app/popup.html", "", "popup,width=400,height=300")')
        popup = self.browser.page('/app/popup.html')
        self.addCleanup(self.browser.close_target, popup)
        wait_for(lambda: popup.eval('!!document.getElementById("out") && innerWidth > 0'
                                    ' && document.visibilityState === "visible"'),
                 what='the popup on screen')
        popup.eval('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
        popup.click('#out')
        wait_for(lambda: popup.eval('location.href') == self.server.url('/out.html?popup'),
                 what='the link in the popup')
        self.assertEqual(popup.eval('opener.location.href'), self.server.url('/app/index.html'))
        self.assertEqual(self.opened(), [])

    def test_blank_form_post_stays_in_oganesson(self):
        app = self.launch_app()
        app.click('#post')
        tab = self.browser.page('/post.html')
        self.addCleanup(self.browser.close_target, tab)
        # The tab shows the URL before the request reaches the server.
        self.assertEqual(wait_for(lambda: self.server.bodies.get('/post.html'),
                                  what='the form post'), b'q=1')
        self.assertEqual(self.opened(), [])

    def test_blank_form_post_with_opener_stays_in_oganesson(self):
        app = self.launch_app()
        app.click('#post-opener')
        tab = self.browser.page('/post-opener.html')
        self.addCleanup(self.browser.close_target, tab)
        # The tab shows the URL before the request reaches the server.
        self.assertEqual(wait_for(lambda: self.server.bodies.get('/post-opener.html'),
                                  what='the form post'), b'q=2')
        self.assertEqual(self.opened(), [])

    def test_script_navigation_from_click_stays_in_app(self):
        # A sign-in button fetching the provider's URL, then assigning it.
        app = self.launch_app()
        app.click('#sign-in')
        wait_for(lambda: app.eval('location.href') == self.server.url('/out.html?assign'),
                 what='the script navigation in the app window')
        self.assertEqual(self.opened(), [])

    def test_in_scope_link_stays_in_app(self):
        app = self.launch_app()
        app.click('#inside')
        wait_for(lambda: app.eval('location.href') == self.server.url('/app/inside.html'),
                 what='the in-scope page in the app window')
        self.assertEqual(self.opened(), [])

    def test_normal_tab_unaffected(self):
        tab = self.browser.new_tab(self.server.url('/app/index.html'))
        wait_for(lambda: tab.eval('location.href') == self.server.url('/app/index.html'),
                 what='the app page in a tab')
        tab.click('#plain')
        wait_for(lambda: tab.eval('location.href') == self.server.url('/out.html?plain'),
                 what='the link in the tab')
        self.assertEqual(self.opened(), [])
        self.browser.close_target(tab)

    def close_out_tabs(self):
        for t in self.browser.targets():
            if t['type'] == 'page' and ('/out.html' in t['url'] or '/app/excluded.html' in t['url']):
                self.browser.close_target(Page(t))

    def test_default_browser_opens_links_in_tabs(self):
        # oganesson as the default browser opens them itself, in tabs of the
        # tabbed window, without xdg-open: from a click, a new window, the
        # link menu and an exclusion.
        self.set_rules(RULES)
        self.make_default_browser()
        self.addCleanup(self.close_out_tabs)
        app = self.launch_app()
        app.click('#plain')
        wait_for(lambda: self.out_tabs(), what='the link in a tab')
        app.click('#blank')
        app.eval('void window.open("/out.html?open")')
        wait_for(lambda: len(self.out_tabs()) == 3, what='three tabs')
        self.browser.click_view(self.link_menu(app, '#plain')[1])
        wait_for(lambda: len(self.out_tabs()) == 4, what='the tab from the menu')
        app.click('#push')
        wait_for(lambda: self.out_tabs('/app/excluded.html'), what='the excluded page in a tab')
        self.assertEqual(sorted(self.out_tabs()), [self.server.url(p) for p in
                                                   ('/out.html?blank', '/out.html?open',
                                                    '/out.html?plain', '/out.html?plain')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))
        self.assertEqual(self.opened(), [])

    def assert_background_tab(self, url):
        """`url` opened in a background tab, and not by xdg-open."""
        tab = self.browser.page(url)
        self.addCleanup(self.browser.close_target, tab)
        self.assertEqual(tab.eval('document.visibilityState', gesture=False), 'hidden')
        self.assertEqual(self.opened(), [])

    def test_default_browser_middle_click_opens_background_tab(self):
        self.make_default_browser()
        app = self.launch_app()
        app.click('#plain', button='middle')
        self.assert_background_tab('/out.html?plain')

    def test_default_browser_menu_background_item_opens_background_tab(self):
        self.make_default_browser()
        app = self.launch_app()
        self.browser.click_view(self.link_menu(app, '#plain')[2])
        self.assert_background_tab('/out.html?plain')

    def test_menu_opens_link_in_default_browser(self):
        # also a link in the app's scope, which a click keeps in the app.
        app = self.launch_app()
        self.browser.click_view(self.link_menu(app, '#inside')[1])
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/inside.html')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))
        self.assertEqual(self.out_tabs('/app/inside.html'), [])

    def test_menu_opens_link_in_default_browser_in_background(self):
        app = self.launch_app()
        self.browser.click_view(self.link_menu(app, '#plain')[2])
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?plain')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))
        self.assertEqual(self.out_tabs(), [])

    def test_menu_names_default_browser(self):
        app = self.launch_app()
        self.set_default_browser_name('Floorp')
        self.wait_link_menu_titles(app, '#plain', ['Open link in Floorp',
                                                   'Open link in Floorp in background'])
        # Another default browser: the open menu takes its name.
        self.set_default_browser_name('Firefox')
        self.wait_link_menu_titles(app, '#plain', ['Open link in Firefox',
                                                   'Open link in Firefox in background'])

    def test_menu_default_browser_name_escaped_and_shortened(self):
        app = self.launch_app()
        # Escaped, an ampersand isn't a mnemonic.
        self.set_default_browser_name('A&B')
        self.wait_link_menu_titles(app, '#plain', ['Open link in A&&B',
                                                   'Open link in A&&B in background'])
        # Cut to 32 characters, "in background" stays in view.
        self.set_default_browser_name('Browser ' * 10)
        short = 'Browser ' * 3 + 'Browser\u2026'
        self.wait_link_menu_titles(app, '#plain', [f'Open link in {short}',
                                                   f'Open link in {short} in background'])


class BrowserTabTest(WebAppTest):
    """In a normal tab, what matches a page to the app follows its scope
    rules: the address bar's "Open in app" icon, and link capturing."""

    def open_in_app_shown(self):
        return any(v.visible and v['TooltipText'] in OPEN_IN_APP
                   for v in self.browser.views('PageActionView'))

    def tab_at(self, path):
        tab = self.browser.new_tab(self.server.url(path))
        self.addCleanup(self.browser.close_target, tab)
        wait_for(lambda: tab.eval('location.pathname') == path
                 and tab.eval('document.readyState') == 'complete', what=path)
        return tab

    def go(self, tab, path):
        tab.eval(f'location.href = {json.dumps(self.server.url(path))}')
        wait_for(lambda: tab.eval('location.pathname') == path
                 and tab.eval('document.readyState') == 'complete', what=path)

    def test_open_in_app_icon_follows_narrowing(self):
        self.set_rules(NARROW)
        tab = self.tab_at('/app/mail/x.html')
        wait_for(self.open_in_app_shown, what='"Open in app" on a page of the rule')
        # In the manifest's scope, but not in the rule on its host.
        self.go(tab, '/app/inside.html')
        wait_for(lambda: not self.open_in_app_shown(), what='"Open in app" gone')

    def test_open_in_app_icon_hidden_on_excluded_page(self):
        self.set_rules(RULES)
        tab = self.tab_at('/app/inside.html')
        wait_for(self.open_in_app_shown, what='"Open in app" in the scope')
        self.go(tab, '/app/excluded.html')
        wait_for(lambda: not self.open_in_app_shown(), what='"Open in app" gone')

    def captured(self, link):
        """Clicks `link` on a normal tab's page; returns whether it opened in
        the app's window rather than a tab."""
        tab = self.tab_at('/links.html')
        path = tab.eval(f'new URL(document.getElementById({json.dumps(link)}).href).pathname')
        before = {t['id'] for t in self.browser.targets()}
        tab.click(f'#{link}')
        target = wait_for(lambda: next((t for t in self.browser.targets() if t['id'] not in before
                                        and t['url'].endswith(path)), None),
                          what=f'{path} opened')
        page = Page(target)
        self.addCleanup(self.browser.close_target, page)
        wait_for(lambda: page.eval('document.readyState') == 'complete', what=path)
        return page.eval('matchMedia("(display-mode: standalone)").matches')

    def capture_links(self):
        self.browser.pipe_call('PWA.changeAppUserSettings', manifestId=self.manifest_id,
                               linkCapturing=True)
        self.addCleanup(self.browser.pipe_call, 'PWA.changeAppUserSettings',
                        manifestId=self.manifest_id, linkCapturing=False)

    def test_captured_links_follow_narrowing(self):
        self.capture_links()
        self.set_rules(NARROW)
        self.assertTrue(self.captured('mail'))
        self.assertFalse(self.captured('inside'))
        self.assertEqual(self.opened(), [])

    def test_captured_links_skip_excluded_page(self):
        self.capture_links()
        self.set_rules(RULES)
        self.assertTrue(self.captured('inside'))
        self.assertFalse(self.captured('excluded'))
        self.assertEqual(self.opened(), [])


class StartUrlTest(WebAppTest):
    """The start address the user sets on chrome://app-settings."""

    def test_launch_opens_start_url(self):
        self.set_start_url(self.server.url('/app/start.html'))
        self.launch_app(url=self.server.url('/app/start.html'))

    def test_desktop_entry_opens_start_url(self):
        # The Exec line of the app's desktop entry, handed to the running
        # browser by a second process.
        self.set_start_url(self.server.url('/app/start.html'))
        self.launch_app(url=self.server.url('/app/start.html'), launch=lambda: subprocess.run(
            [str(self.browser.binary), f'--user-data-dir={self.browser.profile}',
             '--profile-directory=Default', f'--app-id={self.app_id}'],
            env=self.browser.env(), check=True, timeout=60,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

    def test_cleared_start_url_opens_manifest_start_url(self):
        self.set_start_url(self.server.url('/app/start.html'))
        self.assertEqual(self.settings_start_url(''), ['', self.server.url('/app/index.html'), ''])
        self.launch_app()

    def test_start_url_out_of_scope_opens_with_bar(self):
        # Allowed: the window opens there and shows that it is out of the app.
        self.set_start_url(self.server.url('/elsewhere.html', 'localhost'))
        self.launch_app(url=self.server.url('/elsewhere.html', 'localhost'))
        wait_for(self.custom_tab_bar_shown, what='the out-of-app bar')

    def test_start_url_redirected_into_scope(self):
        self.set_start_url(self.server.url('/bounce', 'localhost'))
        self.launch_app(url=self.server.url('/app/start.html'))

    def test_invalid_start_url_rejected(self):
        self.set_start_url(self.server.url('/app/start.html'))
        self.assertEqual(self.settings_start_url('ftp://example.com/'),
                         ['ftp://example.com/', self.server.url('/app/index.html'),
                          'Not an http or https URL: "ftp://example.com/"'])
        self.assertEqual(self.settings_start_url(),
                         [self.server.url('/app/start.html'), self.server.url('/app/index.html'), ''])

    def test_start_url_persists_across_restart(self):
        self.set_start_url(self.server.url('/app/start.html'))
        self.browser.quit()
        prefs = json.loads((self.browser.profile / 'Default/Preferences').read_text())
        self.assertEqual(prefs['oganesson']['web_apps']['user_start_urls'],
                         {self.app_id: self.server.url('/app/start.html')})
        self.browser.start()
        self.launch_app(url=self.server.url('/app/start.html'))

    def test_stored_file_start_url_ignored(self):
        # Set outside the page, as about:config can: launches don't take it.
        self.browser.quit()
        path = self.browser.profile / 'Default/Preferences'
        prefs = json.loads(path.read_text())
        prefs.setdefault('oganesson', {}).setdefault('web_apps', {})['user_start_urls'] = {
            self.app_id: 'file:///etc/hostname'}
        path.write_text(json.dumps(prefs))
        self.browser.start()
        self.addCleanup(self.settings_start_url, '')
        self.launch_app()


class DiyAppTest(WebAppTest):
    """A page without a manifest, installed with "Install page as app…": a
    DIY app, which opens in its own window. It gets all a PWA gets. On
    Linux, Chromium's "Create shortcut…" only puts a desktop shortcut to the
    page, which opens in a tab."""

    app_page = APP_PAGE.replace(b'<link rel="manifest" href="/app/manifest.json">', b'')
    # A DIY app's manifest ID is its start URL, the page installed.
    manifest_path = '/app/index.html'

    @classmethod
    def install(cls):
        browser = cls.browser
        tab = browser.new_tab(cls.manifest_id)
        wait_for(lambda: tab.eval('location.href') == cls.manifest_id, what='the page')
        browser.click_view(browser.wait_view('BrowserAppMenuButton'))
        for menu, title in ((0, '&Save and share'), (1, '&Install page as app…')):
            browser.click_view(wait_for(lambda: next((item for items in browser.menus()[menu:menu + 1]
                                                      for group in items for item in group
                                                      if item['Title'] == title), None),
                                        what=title))
        # The dialog ignores clicks for a moment after it shows or moves:
        # click Install again while it is still there. Since Chromium 157 a
        # bubble then offers to open the tab in the app.
        installed = lambda: tab.eval('!matchMedia("(display-mode: browser)").matches')

        def click_install():
            if installed():
                return True
            for text in ('Install', 'Open tab in app'):
                if any(v.visible for v in browser.views('MdTextButton', Text=text)):
                    browser.click_view(browser.wait_view('MdTextButton', Text=text))
            return installed()
        # The tab moves to the app's new window.
        wait_for(click_install, timeout=30, interval=1, what='the app window')
        browser.close_target(tab)

    def test_plain_link_opens_in_default_browser(self):
        app = self.launch_app()
        app.click('#plain')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?plain')])
        self.assertEqual(self.out_tabs(), [])

    def test_menu_opens_link_in_default_browser(self):
        app = self.launch_app()
        self.browser.click_view(self.link_menu(app, '#inside')[1])
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/inside.html')])
        self.assertEqual(app.eval('location.href'), self.server.url('/app/index.html'))

    def test_user_rule_on_app_site_narrows_scope(self):
        self.set_rules(NARROW)
        app = self.launch_app()
        app.click('#inside')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/inside.html')])

    def test_launch_opens_start_url(self):
        self.set_start_url(self.server.url('/app/start.html'))
        self.launch_app(url=self.server.url('/app/start.html'))


class IsolatedWebAppTest(WebAppTest):
    """An isolated web app, from a dev-mode proxy: its links keep Chromium's
    handling, which opens other origins in a browser tab, and its link menu
    has no default browser items. Hosted (extension) apps can't open
    their window on Linux: Chromium 154 refuses to launch Chrome apps there."""

    browser_args = ('--enable-features=IsolatedWebApps,IsolatedWebAppDevMode',)

    @classmethod
    def install(cls):
        # A proxy-mode bundle ID: 32 bytes and the type 00 00 02, in base32.
        cls.manifest_id = 'isolated-app://{}/'.format(
            base64.b32encode(bytes(32) + b'\0\0\2').decode().rstrip('=').lower())
        cls.server.routes.update({
            '/': (200, {'Content-Type': 'text/html'},
                  f'<!doctype html><a id="plain" href="{cls.server.url("/out.html?iwa")}">out</a>'.encode()),
            '/.well-known/manifest.webmanifest': (200, {'Content-Type': 'application/manifest+json'}, json.dumps({
                'name': 'Isolated', 'version': '1.0.0', 'start_url': '/', 'display': 'standalone',
                'icons': [{'src': '/app/icon.png', 'sizes': '192x192', 'type': 'image/png'}]}).encode()),
        })
        cls.browser.pipe_call('PWA.install', manifestId=cls.manifest_id,
                              installUrlOrBundleUrl=cls.server.url('/'))

    def launch_iwa(self):
        app = self.launch_app(url=self.manifest_id)
        self.wait_on_screen(app)
        return app

    def test_link_stays_in_oganesson(self):
        self.launch_iwa().click('#plain')
        wait_for(lambda: self.out_tabs('/out.html?iwa'), what='the link in a tab')
        self.assertEqual(self.out_tabs('/out.html?iwa'), [self.server.url('/out.html?iwa')])
        self.addCleanup(self.browser.close_target, self.browser.page('/out.html?iwa'))
        self.assertEqual(self.opened(), [])

    def test_menu_has_no_default_browser_items(self):
        self.launch_iwa().click('#plain', button='right')
        titles = [item['Title'] for group in wait_for(self.browser.menus, what='the context menu')[0]
                  for item in group]
        self.close_menus()
        self.assertIn('Open link in new oganesson &tab', titles)
        self.assertEqual([t for t in titles if 'default browser' in t], [])


class OtherHostsTest(WebAppTest):
    """The app on a host with a non-ASCII name (*.localhost needs no
    resolver), and on a literal IPv6 host."""

    app_host = 'xn--bcher-kva.localhost'

    def use_ipv6_host(self):
        """Installs the app from [::1] as well, and has the test use that."""
        self.server = Server(type(self).server.routes, ipv6=True)
        self.addCleanup(self.server.stop)
        self.app_host = '[::1]'
        self.manifest_id = self.server.url(self.manifest_path, self.app_host)
        install_app(self.browser, self.manifest_id, self.server.url('/app/index.html', self.app_host))
        self.app_id = app_id_of(self.manifest_id)

    def test_unicode_rule_on_app_site_narrows_scope(self):
        # The rule spells the host in Unicode; the app's URLs in punycode.
        self.set_rules('http://bücher.localhost:*/app/mail/*')
        app = self.launch_app()
        app.click('#inside')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/inside.html', self.app_host)])

    def test_ipv6_rule_on_app_site_narrows_scope(self):
        self.use_ipv6_host()
        # A pattern's colons start named groups unless escaped.
        self.set_rules(r'http://[\:\:1]:*/app/mail/*')
        app = self.launch_app()
        app.click('#inside')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/app/inside.html', self.app_host)])


class FocusExistingTest(WebAppTest):
    """An app whose launch_handler focuses its open window."""

    manifest_extra = {'launch_handler': {'client_mode': 'focus-existing'}}

    def test_out_of_scope_start_url_navigates_open_window(self):
        # Its launch queue takes only URLs in scope, so the window goes there.
        app = self.launch_app()
        self.set_start_url(self.server.url('/elsewhere.html', 'localhost'))
        before = {t['id'] for t in self.browser.targets()}
        self.browser.pipe_call('PWA.launch', manifestId=self.manifest_id)
        wait_for(lambda: app.eval('location.href') == self.server.url('/elsewhere.html', 'localhost'),
                 what='the open window at the start address')
        self.assertEqual({t['id'] for t in self.browser.targets()
                          if t['type'] == 'page'} - before, set())

    def test_start_url_redirected_into_scope_navigates_open_window(self):
        app = self.launch_app()
        self.set_start_url(self.server.url('/bounce', 'localhost'))
        self.browser.pipe_call('PWA.launch', manifestId=self.manifest_id)
        wait_for(lambda: app.eval('location.href') == self.server.url('/app/start.html'),
                 what='the open window at the redirect target')


class ActivationTokenTest(WebAppTest):
    """On Wayland, where the browser has activation tokens to hand on."""

    wayland = True

    @classmethod
    def setUpClass(cls):
        if not shutil.which('labwc'):
            raise unittest.SkipTest('needs labwc')
        super().setUpClass()

    def test_middle_click_opens_without_token(self):
        # NEW_BACKGROUND_TAB: the default browser stays behind the app.
        app = self.launch_app()
        app.click('#plain', button='middle')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?plain')])
        self.assertEqual(self.tokens_file.read_text().splitlines(), [''])

    def test_plain_click_opens_with_token(self):
        app = self.launch_app()
        app.click('#plain')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?plain')])
        self.assertEqual(self.tokens_file.read_text().splitlines(), ['XDG_ACTIVATION_TOKEN'])

    def test_menu_item_opens_with_token(self):
        app = self.launch_app()
        self.browser.click_view(self.link_menu(app, '#plain')[1])
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?plain')])
        self.assertEqual(self.tokens_file.read_text().splitlines(), ['XDG_ACTIVATION_TOKEN'])

    def test_menu_background_item_opens_without_token(self):
        app = self.launch_app()
        self.browser.click_view(self.link_menu(app, '#plain')[2])
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?plain')])
        self.assertEqual(self.tokens_file.read_text().splitlines(), [''])

    def test_blank_link_opens_with_token(self):
        app = self.launch_app()
        app.click('#blank')
        wait_for(self.opened, what='xdg-open')
        self.assertEqual(self.opened(), [self.server.url('/out.html?blank')])
        self.assertEqual(self.tokens_file.read_text().splitlines(), ['XDG_ACTIVATION_TOKEN'])


class LeavePageDialogTest(WebAppTest):
    """A "Leave this page?" dialog in a regular window leaves an app window
    usable (issue #16): it takes clicks and keys. On Wayland, where the issue
    was seen, when labwc is installed, else on X11, which blocks the same way."""

    wayland = bool(shutil.which('labwc'))

    def test_leave_page_dialog_leaves_app_window_usable(self):
        tab = self.browser.new_tab(self.server.url('/out.html'))
        self.addCleanup(self.browser.close_target, tab)
        # The new tab starts at about:blank, whose readyState is complete too.
        wait_for(lambda: tab.eval('location.pathname == "/out.html"'
                                  ' && document.readyState == "complete"', gesture=False),
                 what='the page')
        # The gesture gives the page the user activation a beforeunload dialog needs.
        tab.eval('addEventListener("beforeunload", e => e.preventDefault())')
        # With Page enabled, the cleanup can close the dialog.
        tab.call('Page.enable')
        # Deferred: setting the location waits for the dialog to close.
        tab.eval('setTimeout(() => location.href = "/elsewhere.html")', gesture=False)
        self.browser.wait_view('MessageBoxView')
        self.addCleanup(tab.call, 'Page.handleJavaScriptDialog', accept=False)

        app = self.launch_app()
        window = self.browser.browser_call('Browser.getWindowForTarget', targetId=app.id)
        self.browser.browser_call('Browser.setWindowBounds', windowId=window['windowId'],
                                  bounds={'windowState': 'maximized'})
        # An input over the whole page, so a click anywhere in the maximized
        # app window lands on it.
        app.eval("""document.body.insertAdjacentHTML('beforeend', '<input id="field"'
                 + ' style="position: fixed; inset: 0; width: 100%; height: 100%">');
                 addEventListener('mousedown', () => window.pressed = true)""", gesture=False)
        wait_for(lambda: app.eval('innerWidth', gesture=False) > 1000, what='the app maximized')
        # Bottom left, away from the dialog in the middle of the other window.
        self.browser.xdotool('mousemove', '200', '800', 'click', '1')
        wait_for(lambda: app.eval('window.pressed === true', gesture=False),
                 what='the click in the app window')
        if self.wayland:
            self.browser.key('a', 'b')
        else:
            # Browser.key focuses the regular window first; with no window
            # manager, focus the app window under the pointer instead.
            found = subprocess.run(['xdotool', 'getmouselocation', '--shell'],
                                   env=self.browser.env(), capture_output=True, text=True,
                                   check=True).stdout
            window = re.search(r'^WINDOW=(\d+)$', found, re.M)[1]
            self.browser.xdotool('windowfocus', '--sync', window)
            self.browser.xdotool('key', 'a', 'b')
        wait_for(lambda: app.eval('field.value', gesture=False) == 'ab',
                 what='the keys in the app window')


if __name__ == '__main__':
    unittest.main()
