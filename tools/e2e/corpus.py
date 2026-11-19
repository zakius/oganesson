#!/usr/bin/env python3
"""The WebExtensions climb's corpus runner (dubna's webextensions/README.md):
the level each add-on of dubna's webextensions/corpus.json reaches in
oganesson.

  corpus.py [--only ID[,ID...]] [--dubna DIR] [--cache DIR] [--jobs N]

Each add-on gets the highest level it passes:

L0  Its manifest is JSON: the install fails, if it does, past that.
L1  It installs as a user's download does: a page of the runner's local
    server goes to the add-on's .xpi with a user gesture, the browser installs
    it packed (InstallUnpackedCrx, through the sandboxed unpacker), and the
    runner accepts the install prompt. Its ID comes from its Gecko ID, or
    without one from AMO's signature (META-INF/mozilla.rsa), as Firefox takes
    it (zakius/dubna#208). An add-on that doesn't install stays at L0 with
    the browser's error, its "Extension error:" line in the log. The levels
    above run on the installed add-on.
L2  Its background page or service worker starts, if it has one, and nothing
    names a missing API or manifest key: its manifest has no key that Firefox
    reads (FIREFOX_KEYS) and no permission that the feature files of the
    build's tree (_manifest_features.json, _permission_features.json) and its
    permission aliases (ALIASES, such as Firefox's "menus" for "contextMenus")
    leave out, and it throws no uncaught error in its first seconds. Such
    an error nearly always comes from an API that isn't there. Any uncaught
    error counts, so the score errs low, but for RACES, errors whose timing
    varies between runs, and FIREFOX_TOO, errors that Firefox gives too.
    Chromium's own warnings for unknown keys don't reach chrome://extensions
    here, hence the feature files.
L3  A smoke check passes, with no new uncaught error from the add-on: its
    toolbar popup, if its browser_action or action has one in its manifest,
    opens on a real click with a web page active (a new page of the add-on
    that chrome.extension.getViews() counts as a popup, or else a new page
    of it in a tab, for an add-on that clears its popup at run time) and
    shows something; and its content
    scripts, if it has some, run on a page they match. That page is the
    runner's own small page, in a tab of the add-on's own, at an https: URL
    made from the first https: or *: pattern of the first entry that runs
    scripts in the isolated world without exclusions (example.com for every
    site; the browser upgrades http: pages), served to that tab alone, so a
    site's content scripts meet a page without the site's markup: the score
    errs low there. That the scripts ran is their isolated world in the
    page; a tab that left the page (another add-on may redirect or close
    it) doesn't count, nor does a popup that closes itself at once. Whether a script changes the page isn't checked: nothing tells
    which add-ons should. A page action's popup isn't checked, as the page
    action shows only where the add-on shows it. An add-on with neither
    reaches L3 at L2.

A full run writes <dubna>/webextensions/score/oganesson.json: the date, the
browser's version, how many add-ons reach each level (or a higher one), and
each add-on's level and the first error that kept it from the next one. With
--only, it runs those add-ons and writes nothing. Either way it prints each
add-on that changed level next to the score it found in the dubna tree before
the run (with --only, every add-on it ran), and exits 1 when one went down a
level. An add-on that went down is run once more first, and the better level
counts: some levels vary between runs.

The add-ons install in groups of GROUP to a browser start, so one bad add-on
doesn't stop the run, and one after another, so each install error is the
add-on's own. --jobs groups run at once, each in a browser of its own (by
default as `./oganesson.py test` does: a quarter of the CPUs, at most 8). The run holds the builds lock ($BUILDS_LOCK, by default
~/dev/.builds.lock). It reads the .xpi files from the cache of dubna's
`tools/amo_corpus.py fetch`, and the browser from OGANESSON_BINARY, by default
the release build in work/.
"""
import argparse
import base64
import datetime
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('OGANESSON_BINARY',
                      str(ROOT / 'work/helium-linux/build/src/out/Release/oganesson'))
os.environ.setdefault('TMPDIR', str(ROOT / 'work/tmp'))
# pylint: disable=wrong-import-position
from harness import (BINARY, DEVELOPER_MODE, Browser, Page, Server, gecko_id, unpack_xpi,
                     wait_for)

LEVELS = ('L0', 'L1', 'L2', 'L3')
GROUP = 20
# The manifest keys that Firefox reads (MDN's manifest.json keys that Firefox
# supports, and experiment_apis from Firefox's schemas), less its metadata,
# which no add-on needs Chromium to read. Firefox does nothing with other keys:
# it warns about an unknown one, such as a "//1" comment, and accepts
# minimum_opera_version without using it. So they don't count.
FIREFOX_KEYS = (
    'action', 'author', 'background', 'browser_action', 'chrome_settings_overrides',
    'chrome_url_overrides', 'commands', 'content_scripts', 'content_security_policy',
    'dark_theme', 'declarative_net_request', 'default_locale', 'description', 'devtools_page',
    'dictionaries', 'experiment_apis', 'homepage_url', 'host_permissions', 'icons',
    'incognito', 'manifest_version', 'name', 'omnibox', 'optional_host_permissions',
    'optional_permissions', 'options_page', 'options_ui', 'page_action', 'permissions',
    'protocol_handlers', 'sandbox', 'short_name', 'sidebar_action', 'theme',
    'theme_experiment', 'user_scripts', 'version', 'web_accessible_resources',
)
# The build's tree, with the feature files.
TREE = BINARY.parents[2]
FEATURES = ('chrome/common/extensions/api/_{}_features.json',
            'extensions/common/api/_{}_features.json')
# Where Chromium names other names for permissions: Alias("alias", "name").
ALIASES = ('chrome/common/extensions/permissions/chrome_api_permissions.cc',
           'extensions/common/permissions/extensions_api_permissions.cc')
# How long the add-ons of a group get to start their backgrounds, and then
# to report errors from their start.
START = 10
SETTLE = 2
# How long an install gets to show its prompt, and then to finish.
INSTALL = 30
# The longest error a score keeps.
ERROR_LENGTH = 300
# Uncaught errors that name no missing API and come and go between runs: a
# message sent at the start before the page that listens for it is up, a
# reply whose page went away before it answered, and a tab gone by the time
# the add-on asks for it (the runner's own tabs).
RACES = ('Receiving end does not exist', 'message channel closed before a response',
         'No tab with id')
# Uncaught errors that Firefox gives too: no add-on may script the browser's
# own pages or another add-on's, and Firefox refuses its about: and other
# moz-extension: pages as well ("Missing host permission for the tab"). An
# add-on that scripts every open tab at its start meets the runner's start
# tab and the other add-ons' pages. Chromium gives the same messages for the
# zoom and debugger calls on such a page, which this can't tell apart: for
# those the score errs high. A content script registered with
# scripting.registerContentScripts() persists across a restart by default, in
# Firefox too, so registering its ID again at the next start is refused there
# as well ("is already registered"); 7TV does it at every start, uncaught.
FIREFOX_TOO = ('Cannot access a chrome:// URL',
               'Cannot access a chrome-extension:// URL of different extension',
               'Duplicate script ID')
# Chromium's other message for another add-on's page, which names it.
OTHER_ADD_ON_PAGE = re.compile(r'Cannot access contents of url "chrome-extension://([a-p]{32})/')
# The smoke check's page for content scripts that run on every site, and the
# page served at every URL of its tabs.
EVERY_SITE = 'https://example.com/'
PAGE = (b'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Corpus page</title>'
        b'</head><body><h1>Corpus page</h1><p>The corpus runner\'s page for content scripts.'
        b' <a href="/">A link</a></p></body></html>')
# Popups pinned to the toolbar at a time, so that their buttons fit.
PINNED = 8
# How long a click gets to open a popup, and a popup to show something.
POPUP = 5


def counts(message, extension):
    """Whether an uncaught error counts against the level of the add-on
    `extension`."""
    other_page = OTHER_ADD_ON_PAGE.search(message)
    return ('Uncaught' in message and not any(text in message for text in RACES + FIREFOX_TOO)
            and not (other_page and other_page[1] != extension))


def feature_file(path):
    """A feature file: JSON with // comments."""
    text = path.read_text()
    kept, in_string, i = [], False, 0
    while i < len(text):
        char = text[i]
        if in_string and char == '\\':
            kept.append(text[i:i + 2])
            i += 2
            continue
        if char == '"':
            in_string = not in_string
        elif not in_string and text.startswith('//', i):
            end = text.find('\n', i)
            i = len(text) if end < 0 else end
            continue
        kept.append(char)
        i += 1
    return json.loads(''.join(kept))


def known(kind):
    """The names Chromium has for `kind`: 'manifest', the top-level keys of a
    manifest, or 'permission', the permissions (some dotted, as
    downloads.open)."""
    names = set()
    for pattern in FEATURES:
        for name in feature_file(TREE / pattern.format(kind)):
            names.add(name.split('.')[0] if kind == 'manifest' else name)
    if kind == 'permission':
        for path in ALIASES:
            text = (TREE / path).read_text()
            for alias, name in re.findall(r'Alias\("([^"]+)", "([^"]+)"\)', text):
                if name in names:
                    names.add(alias)
    return names


def unknown(manifest, keys, permissions):
    """What `manifest` asks for that isn't among `keys` and `permissions`."""
    found = [f"unknown manifest key '{key}'" for key in manifest
             if key in FIREFOX_KEYS and key not in keys]
    for listed in ('permissions', 'optional_permissions'):
        for name in manifest.get(listed) or []:
            if (isinstance(name, str) and '://' not in name and name != '<all_urls>'
                    and name not in permissions):
                found.append(f"unknown permission '{name}'")
    return found


def level(install_error, background, missing, uncaught):
    """The level and the error that kept it from the next one, from what the
    browser showed: `install_error`, its error for a failed install, or None;
    `background`, whether its background started (None: it has none);
    `missing`, what its manifest asks for that Chromium doesn't know
    (unknown()); `uncaught`, its uncaught errors."""
    if install_error:
        return 'L0', install_error
    if background is False:
        return 'L1', uncaught[0] if uncaught else 'the background did not start'
    named = missing + uncaught
    if named:
        return 'L1', named[0]
    return 'L2', None


def content_url(manifest):
    """The URL of a page that the add-on's content scripts run on, for the
    smoke check (L3), or None."""
    for entry in manifest.get('content_scripts') or []:
        if (not isinstance(entry, dict) or not entry.get('js') or entry.get('world') == 'MAIN'
                or any(entry.get(key) for key in ('exclude_matches', 'include_globs',
                                                  'exclude_globs'))):
            continue
        for pattern in entry.get('matches') or []:
            if pattern == '<all_urls>':
                return EVERY_SITE
            # Only https: the browser upgrades a page from http: to https:.
            found = re.fullmatch(r'(\*|https)://([^/:]+)(/.*)', str(pattern))
            if not found:
                continue
            host, path = found[2], found[3].replace('*', '')
            if host == '*':
                host = EVERY_SITE.split('/')[2]
            elif host.startswith('*.'):
                host = 'www.' + host[2:]
            if '*' not in host:
                return f'https://{host}{path}'
    return None


def has_popup(manifest):
    """Whether the add-on's toolbar button has a popup in its manifest."""
    for key in ('browser_action', 'action'):
        action = manifest.get(key)
        if isinstance(action, dict) and action.get('default_popup'):
            return True
    return False


def serve(browser, url):
    """A new tab at `url`, where the runner serves PAGE, with the tab's
    execution contexts kept in its `events`. Later navigations of the tab go
    to the network."""
    page = browser.new_tab('about:blank')
    try:
        page.call('Runtime.enable')
        page.call('Fetch.enable', patterns=[{'urlPattern': '*', 'resourceType': 'Document'}])
        page.next_id += 1
        navigation = page.next_id
        page.ws.send(json.dumps({'id': navigation, 'method': 'Page.navigate',
                                 'params': {'url': url}}))
        while True:
            message = json.loads(page.ws.recv())
            if message.get('method') == 'Fetch.requestPaused':
                page.next_id += 1
                page.ws.send(json.dumps({'id': page.next_id, 'method': 'Fetch.fulfillRequest',
                                         'params': {
                    'requestId': message['params']['requestId'], 'responseCode': 200,
                    'responseHeaders': [{'name': 'Content-Type', 'value': 'text/html'}],
                    'body': base64.b64encode(PAGE).decode()}}))
            elif message.get('id') == navigation:
                break
            elif 'method' in message:
                page.events.append(message)
        page.call('Fetch.disable')
        # As the browser writes it, to tell later whether the tab left it.
        page.served = page.eval('location.href')
    except Exception:
        close(browser, page)
        raise
    return page


def set_pinned(browser, extensions, pinned):
    page = browser.new_tab('chrome://extensions')
    try:
        wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
        for extension in extensions:
            # An add-on may have removed itself since (management.uninstallSelf).
            page.eval('chrome.developerPrivate.updateExtensionConfiguration('
                      f'{{extensionId: {json.dumps(extension)}, '
                      f'pinnedToToolbar: {json.dumps(pinned)}}}).catch(() => {{}})')
    finally:
        close(browser, page)


def is_popup(target):
    """Whether the page `target` is its add-on's toolbar popup, or None while
    it can't tell."""
    try:
        page = Page(target)
    except OSError:
        return None
    page.ws.sock.settimeout(POPUP)
    try:
        return page.eval("document.readyState == 'complete' ? "
                         "!!chrome.extension?.getViews?.({type: 'popup'}).includes(window) : null",
                         gesture=False)
    except (OSError, AssertionError):
        return None
    finally:
        page.close()


def shows_something(target):
    """None when the popup `target` shows something, else why not."""
    try:
        popup = Page(target)
    except OSError:
        return None  # It closed itself at once (window.close()).
    # A popup that a dialog (alert()) holds never answers.
    popup.ws.sock.settimeout(POPUP)
    shows = ("[...document.querySelectorAll('body *')].some(e => {"
             " const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })")
    try:
        wait_for(lambda: popup.eval(shows, gesture=False), timeout=POPUP)
        return None
    except AssertionError:
        return 'the popup shows nothing'
    except OSError:
        return 'the popup does not answer'
    finally:
        popup.close()


def open_popups(browser, extensions):
    """Clicks the toolbar buttons of the add-ons `extensions`, whose actions
    have popups, and returns {extension: None, or why its popup failed} for
    the popups that opened."""
    found = {}
    for start in range(0, len(extensions), PINNED):
        batch = extensions[start:start + PINNED]
        set_pinned(browser, batch, True)
        # Which button is which shows only by the popup a click opens: the
        # tooltips are the add-ons' titles, which only the browser has
        # localized, and the bundled uBlock Origin's button is there too.
        views = browser.wait_settled(lambda: [v for v in browser.views('ToolbarActionView')
                                              if v.visible] or None, what='the toolbar buttons')
        for view in views:
            before = {t['id'] for t in browser.targets()}
            browser.click_view(view)
            # A new page of an add-on of the batch that is its popup, not
            # another page that an add-on opened meanwhile.
            checked = {}

            def popup(before=before, checked=checked):
                for target in browser.targets():
                    extension = target['url'].split('/')[2] if '://' in target['url'] else ''
                    if (target['id'] in before or target['type'] != 'page'
                            or extension not in batch or extension in found):
                        continue
                    if checked.get(target['id']) is None:
                        checked[target['id']] = is_popup(target)
                    if checked[target['id']]:
                        return target
                return None

            try:
                target = wait_for(popup, timeout=POPUP, what='a popup')
            except AssertionError:
                # Another popup, the bundled uBlock Origin's, may be open: it
                # would take the next click.
                browser.key('Escape')
                # An add-on that clears its popup at run time opens its page in
                # a tab instead.
                target = next((t for t in browser.targets() if t['id'] not in before
                               and t['type'] == 'page' and '://' in t['url']
                               and t['url'].split('/')[2] in batch
                               and t['url'].split('/')[2] not in found), None)
                if not target:
                    continue
            extension = target['url'].split('/')[2]
            found[extension] = shows_something(target)
            close(browser, types.SimpleNamespace(id=target['id']))
        set_pinned(browser, batch, False)
    return found


def smoke_check(browser, extensions, manifests):
    """The smoke check (L3) of the add-ons `extensions` {item: extension ID},
    with their `manifests`: {item: error or None}, from what they did in it.
    Their uncaught errors are read afterwards."""
    errors = {}
    tabs = {}
    try:
        # A tab for each add-on, so that one that takes a tab elsewhere (a
        # redirect) doesn't take another's. The page for every site last, so
        # that it is the active tab for the popups, as a web page where a
        # user opens one.
        urls = {item: content_url(manifests[item]) for item in extensions}
        for item, url in sorted(urls.items(), key=lambda pair: pair[1] == EVERY_SITE):
            if url:
                try:
                    tabs[item] = serve(browser, url)
                except (OSError, AssertionError, RuntimeError):
                    pass  # Another add-on closed it: it doesn't tell.
        popups = [extensions[i] for i in extensions if has_popup(manifests[i])]
        opened = open_popups(browser, popups) if popups else {}
        for item, extension in extensions.items():
            if extension in popups:
                errors[item] = opened.get(extension, 'the popup did not open')
        time.sleep(SETTLE)
        for item, tab in tabs.items():
            # A tab that left the page doesn't tell: another add-on may have
            # taken it, or closed it.
            try:
                if errors.get(item) or tab.eval('location.href') != tab.served:
                    continue
            except (OSError, AssertionError, RuntimeError):
                continue
            worlds = {e['params']['context'].get('origin') for e in tab.events
                      if e['method'] == 'Runtime.executionContextCreated'
                      and e['params']['context'].get('auxData', {}).get('type') == 'isolated'}
            if f'chrome-extension://{extensions[item]}' not in worlds:
                errors[item] = f'its content scripts did not run on {tab.served}'
    finally:
        for tab in tabs.values():
            close(browser, tab)
    return {item: errors.get(item) for item in extensions}


def close(browser, page):
    """Closes `page`, which may have closed itself (window.close())."""
    try:
        browser.close_target(page)
    except (OSError, AssertionError):
        pass


def read_manifest(folder):
    """The add-on's manifest, or {} when it doesn't parse."""
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def signature_id(folder):
    """The ID in the add-on's AMO signature: the first common name of the
    certificates in META-INF/mozilla.rsa that is a Gecko ID, as dubna's
    firefox_xpi_signature.cc reads it, or None."""
    signature = folder / 'META-INF' / 'mozilla.rsa'
    if not signature.is_file():
        return None
    certificates = subprocess.run(
        ['openssl', 'pkcs7', '-inform', 'DER', '-in', str(signature), '-print_certs', '-noout'],
        capture_output=True, text=True, check=False).stdout
    for name in re.findall(r'^subject=.*?CN ?= ?([^,/\n]+)', certificates, re.M):
        if gecko_id({'browser_specific_settings': {'gecko': {'id': name.strip()}}}):
            return name.strip()
    return None


def installed_id(folder, manifest):
    """The ID of the add-on installed from its .xpi, which dubna's
    firefox_xpi_installer.cc makes from its Gecko ID (the key in the manifest
    doesn't count), or from its AMO signature's ID, or None: without either it
    doesn't install."""
    found = gecko_id(manifest) or signature_id(folder)
    if not found:
        return None
    digest = hashlib.sha256(found.encode()).hexdigest()[:32]
    return digest.translate(str.maketrans('0123456789abcdef', 'abcdefghijklmnop'))


def backgrounds(browser):
    """The add-ons whose background page or service worker runs."""
    return {t['url'].split('/')[2] for t in browser.targets()
            if t['type'] in ('background_page', 'service_worker')
            and t['url'].startswith('chrome-extension://')}


def install(browser, server, path, extension, extensions_page, started):
    """Installs the add-on `extension` from its .xpi at `path` of `server` as
    a user's download does, accepting the install prompt, and returns None,
    or else the browser's error. `extensions_page` is a chrome://extensions
    tab. The add-ons whose backgrounds run meanwhile join `started`."""
    log_start = len(browser.log_path.read_text(errors='replace'))

    def error():
        log = browser.log_path.read_text(errors='replace')[log_start:]
        found = next((line.split('Extension error: ', 1)[1] for line in log.splitlines()
                      if 'Extension error: ' in line), None)
        # "Failed to load extension from: <the download's path>. <error>"
        return found and found.split('.xpi. ', 1)[-1]

    def installed():
        # A background seen once counts: an add-on may remove itself after
        # its start (management.uninstallSelf).
        started.update(backgrounds(browser))
        return extension in started or extensions_page.eval(
            'new Promise(r => chrome.developerPrivate.getExtensionsInfo('
            '{includeDisabled: true, includeTerminated: true}, '
            f'all => r(all.some(e => e.id === {json.dumps(extension)}))))')

    def prompt():
        return [v for v in browser.views('MdTextButton', Text='Add extension') if v.visible]

    tab = browser.download(server.url('/'), path)
    try:
        # A theme installs without a prompt, and a broken add-on fails before it.
        wait_for(lambda: error() or installed() or prompt(), timeout=INSTALL,
                 what='the install prompt')
        if not (error() or installed()):
            browser.accept_install_prompt()
            wait_for(lambda: error() or installed(), timeout=INSTALL, what='the install')
        return error()
    finally:
        close(browser, tab)


def console_message(line):
    """A console line of browser.log, as `"<message>", source: <url> (<line>)`,
    as the message and the file and line it came from."""
    found = re.search(r'"(.*)", source: chrome-extension://[^/]+/(\S*) \((\d+)\)', line)
    return f'{found[1]} ({found[2]}:{found[3]})' if found else line.split('CONSOLE', 1)[1]


def installed_info(browser):
    """What chrome://extensions knows of each add-on: {ID: ExtensionInfo}."""
    page = browser.new_tab('chrome://extensions')
    try:
        # The new tab is blank until the page commits, without the API.
        wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
        return {e['id']: e for e in page.eval(
            'new Promise(r => chrome.developerPrivate.getExtensionsInfo('
            '{includeDisabled: true, includeTerminated: true}, r))')}
    finally:
        browser.close_target(page)


def uncaught_errors(extension, log, info):
    """The uncaught errors that count against the add-on `extension`: its
    console lines in the browser's `log`, and its runtime errors in `info`,
    its ExtensionInfo, if it has one."""
    # Its own console lines: another add-on's error may name this one's page
    # in its message ("Cannot access contents of url").
    found = [console_message(line) for line in log.splitlines()
             if 'CONSOLE' in line and f'", source: chrome-extension://{extension}/' in line
             and counts(line, extension)]
    if info:
        found += [e['message'] for e in info.get('runtimeErrors', [])
                  if counts(e['message'], extension)]
    return found


def smoke_levels(browser, at_l2, manifests, installed, log):
    """The levels {item: (level, error)} of the add-ons at L2 `at_l2`
    {item: extension ID} after the smoke check, from what chrome://extensions
    knew of them (`installed`) and the browser's `log` when L2 was read."""
    checked = smoke_check(browser, at_l2, manifests)
    later = installed_info(browser)
    new_log = browser.log_path.read_text(errors='replace')[len(log):]
    levels = {}
    for item_id, extension in at_l2.items():
        # Only what the add-on threw since L2 was read.
        seen = len((installed.get(extension) or {}).get('runtimeErrors', []))
        info = later.get(extension)
        if info:
            info = {**info, 'runtimeErrors': info.get('runtimeErrors', [])[seen:]}
        error = checked[item_id] or next(iter(uncaught_errors(extension, new_log, info)), None)
        levels[item_id] = ('L2', error[:ERROR_LENGTH]) if error else ('L3', None)
    return levels


def run_group(items, xpis, work):
    """Installs the add-ons `items` (corpus entries) from their .xpi files
    `xpis` in one browser and returns {id: (level, error)}."""
    folders = {}
    for item, xpi in zip(items, xpis):
        folder = work / item['sha256']
        try:
            folders[item['id']] = unpack_xpi(xpi, folder)
        except Exception as error:  # pylint: disable=broad-except
            folders[item['id']] = None
            print(f"{item['id']}: {error}", file=sys.stderr)
    results = {i: (None, 'the .xpi does not unpack') for i, f in folders.items() if not f}
    if not any(folders.values()):
        return results
    keys, permissions = known('manifest'), known('permission')
    routes = {'/': (200, {'Content-Type': 'text/html'}, b'<p>Add-ons</p>')}
    for number, xpi in enumerate(xpis):
        routes[f'/{number}.xpi'] = (200, {'Content-Type': 'application/x-xpinstall'},
                                    xpi.read_bytes())
    # --noerrdialogs: a failed install would hold the run with a message box.
    browser = Browser(args=['--noerrdialogs'], prefs=DEVELOPER_MODE)
    server = Server(routes)
    try:
        manifests = {i: read_manifest(f) for i, f in folders.items() if f}
        ids = {i: installed_id(folders[i], m) for i, m in manifests.items()}
        started = set()
        extensions_page = browser.new_tab('chrome://extensions')
        wait_for(lambda: extensions_page.eval('!!chrome.developerPrivate'),
                 what='chrome://extensions')
        install_errors = {}
        for number, item in enumerate(items):
            if folders[item['id']]:
                install_errors[item['id']] = install(browser, server, f'/{number}.xpi',
                                                     ids[item['id']], extensions_page, started)
        close(browser, extensions_page)
        # An install pins its add-on, so a group's buttons overflow the
        # toolbar: the smoke check pins a few at a time.
        set_pinned(browser, [ids[i] for i, error in install_errors.items() if not error], False)
        # L2 and L3 run on a browser that starts with the add-ons installed,
        # as they did with --load-extension: while they installed, their
        # content scripts met the runner's own pages, and their errors there
        # would count at L2. A background seen during the installs counts.
        browser.quit()
        restart = len(browser.log_path.read_text(errors='replace'))
        browser.start()
        expected = {ids[i] for i, error in install_errors.items()
                    if not error and manifests[i].get('background')}
        # Every background that will start, or the end of START.
        deadline = time.monotonic() + START
        while time.monotonic() < deadline:
            started |= backgrounds(browser)
            if expected <= started:
                break
            time.sleep(0.5)
        time.sleep(SETTLE)
        installed = installed_info(browser)
        log = browser.log_path.read_text(errors='replace')
        for item_id, install_error in install_errors.items():
            if install_error and not manifests[item_id]:
                # Not JSON: the browser refuses it for want of a Gecko ID.
                results[item_id] = (None, 'its manifest does not parse')
                continue
            extension = ids[item_id]
            info = installed.get(extension)
            uncaught = uncaught_errors(extension, log[restart:], info)
            background = (extension in started) if manifests[item_id].get('background') else None
            found, error = level(install_error, background,
                                 unknown(manifests[item_id], keys, permissions), uncaught)
            results[item_id] = (found, error and error[:ERROR_LENGTH])
        at_l2 = {i: ids[i] for i, (found, _) in results.items() if found == 'L2'}
        if at_l2:
            try:
                results.update(smoke_levels(browser, at_l2, manifests, installed, log))
            except Exception as error:  # pylint: disable=broad-except
                # The runner's failure, not the add-ons': they stay at L2.
                for item_id in at_l2:
                    results[item_id] = ('L2', f'the smoke check failed: {error}'[:ERROR_LENGTH])
    finally:
        server.stop()
        browser.stop()
    return results


def run_safely(items, xpis, work):
    """run_group(), and when the browser fails with a group, each add-on of it
    alone: one that the browser still fails with gets L0 and the failure. So
    too for each add-on whose smoke check failed in a group."""
    try:
        results = run_group(items, xpis, work)
    except Exception as error:  # pylint: disable=broad-except
        if len(items) == 1:
            return {items[0]['id']: ('L0', f'the browser failed: {error}'[:ERROR_LENGTH])}
        results = {}
        for number, (item, xpi) in enumerate(zip(items, xpis)):
            results.update(run_safely([item], [xpi], work / f'alone-{number}'))
        return results
    # One add-on's popup can end its group's smoke check, as OneTab's, which
    # closes every tab: the add-ons it stopped are checked again alone.
    if len(items) > 1:
        for number, (item, xpi) in enumerate(zip(items, xpis)):
            error = results.get(item['id'], (None, None))[1] or ''
            if error.startswith('the smoke check failed'):
                alone = run_safely([item], [xpi], work / f'alone-{number}')[item['id']]
                # Alone, an install can fail by itself: the better level counts.
                if LEVELS.index(alone[0] or 'L0') >= LEVELS.index(results[item['id']][0]):
                    results[item['id']] = alone
    return results


def version():
    out = subprocess.run([str(BINARY), '--version'], capture_output=True, text=True, check=False)
    return out.stdout.strip()


def at_least(found, name):
    return found is not None and LEVELS.index(found) >= LEVELS.index(name)


def went_down(before, now):
    """Whether an add-on at `before` in the score is lower `now`."""
    return at_least(before, 'L0') and not at_least(now, before)


def run_all(corpus, xpis, work, jobs, report):
    """run_safely() for each group of the corpus, `jobs` groups at once:
    {id: (level, error)}. With `report`, prints the counts after each group,
    in the corpus's order."""
    starts = range(0, len(corpus), GROUP)
    results = {}
    with ThreadPoolExecutor(jobs) as pool:
        groups = pool.map(lambda start: run_safely(corpus[start:start + GROUP],
                                                   xpis[start:start + GROUP],
                                                   work / str(start)), starts)
        try:
            for group in groups:
                results.update(group)
                if report:
                    l2 = sum(1 for r in results.values() if at_least(r[0], 'L2'))
                    l3 = sum(1 for r in results.values() if r[0] == 'L3')
                    print(f'{len(results)} of {len(corpus)} add-ons, {l2} at L2 or higher, '
                          f'{l3} at L3', flush=True)
        except BaseException:
            # An interrupt reaches this thread alone: start no more groups.
            # The running ones end by themselves, a few minutes at most.
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    return results


def hold_builds_lock():
    lock = open(os.environ.get('BUILDS_LOCK', Path.home() / 'dev/.builds.lock'), 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('corpus.py: waiting for the builds lock', file=sys.stderr, flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
    return lock  # held until the process exits


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', help='the Gecko IDs of the add-ons to run, comma-separated')
    parser.add_argument('--dubna', type=Path, default=ROOT / 'dubna',
                        help='the dubna checkout: its corpus.json, and the score it gets')
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/dubna-amo-corpus',
                        help='the .xpi files of amo_corpus.py fetch')
    parser.add_argument('-j', '--jobs', type=int, default=max(1, min(8, os.cpu_count() // 4)),
                        help='how many groups run at once')
    args = parser.parse_args()
    if not BINARY.is_file():
        sys.exit(f'no browser binary at {BINARY}; run ./oganesson.py build --release')
    corpus = json.loads((args.dubna / 'webextensions/corpus.json').read_text())
    score_path = args.dubna / 'webextensions/score/oganesson.json'
    if args.only:
        only = set(args.only.split(','))
        corpus = [item for item in corpus if item['id'] in only]
        if len(corpus) != len(only):
            sys.exit(f"not in the corpus: {only - {item['id'] for item in corpus}}")
    xpis = [args.cache / f"{item['sha256']}.xpi" for item in corpus]
    absent = [x for x in xpis if not x.is_file()]
    if absent:
        sys.exit(f'{len(absent)} .xpi files are not in {args.cache}; '
                 'run dubna/tools/amo_corpus.py fetch')
    # Read first: a full run writes the file.
    old = json.loads(score_path.read_text())['addons'] if score_path.is_file() else {}
    lock = hold_builds_lock()  # noqa: F841 (held until exit)
    with tempfile.TemporaryDirectory(prefix='oganesson-corpus-') as work:
        results = run_all(corpus, xpis, Path(work) / 'run', args.jobs, True)
        dropped = [n for n, item in enumerate(corpus)
                   if went_down(old.get(item['id'], {}).get('level'), results[item['id']][0])]
        if dropped:
            print(f'{len(dropped)} add-ons went down: running them once more', flush=True)
            again = run_all([corpus[n] for n in dropped], [xpis[n] for n in dropped],
                            Path(work) / 'again', args.jobs, False)
            for item_id, result in again.items():
                if LEVELS.index(result[0] or 'L0') > LEVELS.index(results[item_id][0] or 'L0'):
                    results[item_id] = result
    addons = {item['id']: {'level': results[item['id']][0], 'error': results[item['id']][1]}
              for item in corpus}
    down = False
    for item_id, result in addons.items():
        before = old.get(item_id, {}).get('level')
        down = down or went_down(before, result['level'])
        if args.only or before != result['level']:
            print(f"{item_id}: {before or '-'} -> {result['level'] or '-'}"
                  f"{'  DOWN' if went_down(before, result['level']) else ''}"
                  f"  {result['error'] or ''}")
    if args.only:
        return 1 if down else 0
    score = {
        'date': datetime.date.today().isoformat(),
        'browser': version(),
        'levels': {name: sum(1 for a in addons.values() if at_least(a['level'], name))
                   for name in LEVELS},
        'addons': addons,
    }
    score_path.parent.mkdir(exist_ok=True)
    score_path.write_text(json.dumps(score, indent=1, ensure_ascii=False) + '\n')
    print(f"{score_path}: {', '.join(f'{k} {v}' for k, v in score['levels'].items())}")
    return 1 if down else 0


if __name__ == '__main__':
    sys.exit(main())
