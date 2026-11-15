"""Firefox add-ons (dubna's webextensions/README.md): Firefox's WebExtensions
APIs that Chromium lacks, as an add-on from AMO calls them. One test per API,
each on the same small Manifest V2 add-on, as most of AMO's are. An add-on in
the profile's firefox_add_ons.named_firefox list is told it runs in Firefox."""

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from harness import (DEVELOPER_MODE, BrowserTest, Page, Server, extension_id, unpack_xpi,
                     wait_for)

ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox APIs test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-apis@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['menus', 'storage'],
    }),
    'background.js': '''
        browser.menus.create({id: 'firefox-item', title: 'Firefox menu item', contexts: ['page']});
        browser.menus.onClicked.addListener(info => { self.clicked = info.menuItemId; });
        self.started = true;
    ''',
}


class FirefoxAddOnsTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-add-on-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def background_eval(self, js):
        background = self.browser.extension_background(extension_id(self.unpacked))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            return background.eval(js)
        finally:
            background.close()

    def test_runtime_get_browser_info(self):
        # The promise form, and the callback form older add-ons use.
        info = self.background_eval('browser.runtime.getBrowserInfo()')
        same = self.background_eval('new Promise(done => chrome.runtime.getBrowserInfo(done))')
        self.assertEqual(info, same)
        self.assertEqual(sorted(info), ['buildID', 'name', 'vendor', 'version'])
        # The browser's own name: add-ons compare it with "Firefox" to work
        # around Firefox's bugs. Chromium's version, past every Firefox
        # version an add-on checks for.
        self.assertEqual(info['name'], 'oganesson')
        self.assertRegex(info['version'], r'^\d+\.\d+\.\d+\.\d+$')
        self.assertGreaterEqual(int(info['version'].split('.')[0]), 157)

    def test_storage_session(self):
        # Firefox has storage.session in Manifest V2 too (Ghostery, KeePassXC):
        # the promise form and the callback form. setAccessLevel only has to
        # be there, as RoSeal looks for it; what it changes is Chromium's.
        result = self.background_eval('''(async () => {
            await browser.storage.session.set({key: 'value'});
            return {
                stored: await browser.storage.session.get('key'),
                callback: await new Promise(done => chrome.storage.session.get(['key'], done)),
                accessLevel: await browser.storage.session.setAccessLevel(
                    {accessLevel: 'TRUSTED_CONTEXTS'}).then(() => 'set', error => error.message),
            };
        })()''')
        self.assertEqual(result, {'stored': {'key': 'value'}, 'callback': {'key': 'value'},
                                  'accessLevel': 'set'})

    def click_page_menu_item(self):
        """Opens a page's context menu, clicks the add-on's item and returns
        the titles of the menu's items."""
        page = self.browser.new_tab('data:text/html,<body%20style=height:90vh>')
        try:
            wait_for(lambda: page.eval("location.protocol == 'data:' && document.readyState == 'complete'"),
                     what='the page')
            self.browser.click_element(page, 'body', button=3)
            item = wait_for(lambda: next((i for menu in self.browser.menus() for group in menu
                                          for i in group if i['Title'] == 'Firefox menu item'), None),
                            what='the add-on\'s menu item')
            titles = [i['Title'] for menu in self.browser.menus() for group in menu for i in group]
            self.browser.click_view(item)
            wait_for(lambda: not self.browser.menus(), what='the menu to close')
            return titles
        finally:
            self.browser.close_target(page)

    def test_menus(self):
        # Firefox's name for contextMenus, with its permission: the item shows
        # in the page's context menu, and a click reaches the add-on.
        self.background_eval('true')  # The background has created the item.
        self.click_page_menu_item()
        self.assertEqual(self.background_eval('self.clicked'), 'firefox-item')

    def test_menus_firefox_properties(self):
        # Firefox's item icons and the contexts this browser doesn't offer:
        # create and update take them, the item shows in its other contexts,
        # and an item with only such contexts shows in no page menu.
        errors = self.background_eval('''self.clicked = null; browser.menus.remove('tools-item').catch(() => {})
          .then(() => Promise.all([
            new Promise(done => browser.menus.create(
                {id: 'tools-item', title: 'Firefox Tools menu item',
                 contexts: ['tools_menu', 'bookmark'], icons: {16: 'icon.png'}},
                () => done(chrome.runtime.lastError ? chrome.runtime.lastError.message : null))),
            browser.menus.update('firefox-item', {contexts: ['page', 'password'],
                                                  icons: {16: 'icon.png', 32: 'icon.png'}})
                .then(() => null, error => error.message),
          ]))''')
        self.assertEqual(errors, [None, None])
        titles = self.click_page_menu_item()
        self.assertNotIn('Firefox Tools menu item', titles)
        self.assertEqual(self.background_eval('self.clicked'), 'firefox-item')


class FirefoxNamedTest(FirefoxAddOnsTest):
    """The same add-on, listed by its Gecko ID in the profile's list of add-ons
    that are told they run in Firefox."""
    prefs = {'firefox_add_ons': {'named_firefox': ['firefox-apis@oganesson.test']}}

    def test_runtime_get_browser_info(self):
        info = self.background_eval('browser.runtime.getBrowserInfo()')
        self.assertEqual((info['name'], info['vendor']), ('Firefox', 'Mozilla'))
        self.assertGreaterEqual(int(info['version'].split('.')[0]), 157)


SIDEBAR_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox sidebar test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-sidebar@oganesson.test'}},
        'sidebar_action': {'default_panel': 'panel.html', 'default_title': 'Test sidebar'},
    }),
    'panel.html': '<!doctype html><title>Test sidebar</title><p>The sidebar panel</p>',
}


class FirefoxSidebarTest(BrowserTest):
    """sidebar_action: an add-on with only Firefox's sidebar, as Sidebery and
    Tree Style Tab have it, opens it as its side panel from its toolbar menu."""
    # The bundled uBlock Origin's button comes into the toolbar after the
    # start and moves the add-on's button: the right-click would hit uBlock's.
    wait_ubo = True

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-sidebar-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in SIDEBAR_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_sidebar_action(self):
        add_on = extension_id(self.unpacked)
        # The key is known: no "Unrecognized manifest key" warning.
        errors = self.browser.extension_errors(add_on)
        self.assertFalse([e for e in errors if 'sidebar_action' in e], errors)
        button = self.browser.toolbar_button(add_on)
        self.browser.click_view(button, button=3)
        item = wait_for(lambda: next((i for menu in self.browser.menus() for group in menu
                                      for i in group if i['Title'] == 'Open side panel'), None),
                        what='"Open side panel" in the add-on\'s menu')
        self.browser.click_view(item)
        panel = wait_for(lambda: next((t for t in self.browser.targets()
                                       if t['url'] == f'chrome-extension://{add_on}/panel.html'),
                                      None), what='the side panel')
        page = Page(panel)
        try:
            wait_for(lambda: page.eval("document.readyState == 'complete'"), what='the panel page')
            self.assertEqual(page.eval('document.body.innerText'), 'The sidebar panel')
        finally:
            page.close()


def mv3_add_on(name, background, files):
    """A Firefox Manifest V3 add-on whose background is `background`."""
    manifest = {
        'manifest_version': 3,
        'name': f'Firefox MV3 {name} test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': f'firefox-mv3-{name}@oganesson.test'}},
        'background': background,
    }
    return {'manifest.json': json.dumps(manifest), **files}


MV3_ADD_ONS = {
    # Firefox's own: an event page from scripts, or from a page.
    'scripts': mv3_add_on('scripts', {'scripts': ['background.js']},
                          {'background.js': 'self.started = "page";'}),
    'page': mv3_add_on('page', {'page': 'background.html'},
                       {'background.html': '<!doctype html><script src="background.js"></script>',
                        'background.js': 'self.started = "page";'}),
    # For Firefox and Chromium both: each browser takes its own key.
    'both': mv3_add_on('both', {'scripts': ['background.js'], 'service_worker': 'worker.js'},
                       {'background.js': 'self.started = "page";',
                        'worker.js': 'self.started = "worker";'}),
}


class FirefoxManifestV3Test(BrowserTest):
    """Firefox's Manifest V3 backgrounds: background.scripts and
    background.page run as a background page, and a manifest with a service
    worker too runs the worker, as Chromium does."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-mv3-'))
        cls.unpacked = {}
        for name, files in MV3_ADD_ONS.items():
            xpi = cls.folder / f'{name}.xpi'
            with zipfile.ZipFile(xpi, 'w') as archive:
                for file, text in files.items():
                    archive.writestr(file, text)
            cls.unpacked[name] = unpack_xpi(xpi, cls.folder / name)
        cls.browser_args = ('--load-extension=' + ','.join(str(f) for f in cls.unpacked.values()),)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def check_background(self, name, kind, started):
        add_on = extension_id(self.unpacked[name])
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started') == started, what=f'the {name} background')
        finally:
            background.close()
        prefix = f'chrome-extension://{add_on}/'
        self.assertEqual([t['type'] for t in self.browser.targets() if t['url'].startswith(prefix)],
                         [kind])
        errors = self.browser.extension_errors(add_on)
        self.assertFalse([e for e in errors if 'background' in e], errors)

    def test_background_scripts(self):
        self.check_background('scripts', 'background_page', 'page')

    def test_background_page(self):
        self.check_background('page', 'background_page', 'page')

    def test_service_worker_too(self):
        self.check_background('both', 'service_worker', 'worker')

    def test_get_contexts(self):
        # Duplicate Tabs Closer calls it at its start. Chromium, which has no
        # Manifest V3 background page, aborted on finding one.
        add_on = extension_id(self.unpacked['scripts'])
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started') == 'page', what='the background')
            contexts = background.eval('browser.runtime.getContexts({})')
        finally:
            background.close()
        self.assertEqual([(c['contextType'], c['documentUrl']) for c in contexts],
                         [('BACKGROUND', f'chrome-extension://{add_on}/_generated_background_page.html')])


def module_add_on(manifest_version):
    """A Firefox add-on whose module background imports another file."""
    manifest = {
        'manifest_version': manifest_version,
        'name': f'Firefox MV{manifest_version} module test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': f'firefox-module-{manifest_version}@oganesson.test'}},
        'background': {'scripts': ['background.js'], 'type': 'module'},
    }
    return {
        'manifest.json': json.dumps(manifest),
        'background.js': "import {name} from './name.js'; self.started = name(import.meta.url);",
        'name.js': "export function name(url) { return url.split('/').pop(); }",
    }


MODULE_ADD_ONS = {'mv2': module_add_on(2), 'mv3': module_add_on(3)}


class FirefoxModuleBackgroundTest(BrowserTest):
    """A background with "type": "module", in Manifest V2 and V3: its
    scripts load as modules, so they can import and read import.meta."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-module-'))
        cls.unpacked = {}
        for name, files in MODULE_ADD_ONS.items():
            xpi = cls.folder / f'{name}.xpi'
            with zipfile.ZipFile(xpi, 'w') as archive:
                for file, text in files.items():
                    archive.writestr(file, text)
            cls.unpacked[name] = unpack_xpi(xpi, cls.folder / name)
        cls.browser_args = ('--load-extension=' + ','.join(str(f) for f in cls.unpacked.values()),)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def check_module(self, name):
        add_on = extension_id(self.unpacked[name])
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started') == 'background.js',
                     what=f'the {name} module background')
        finally:
            background.close()
        errors = self.browser.extension_errors(add_on)
        self.assertFalse([e for e in errors if 'background' in e or 'module' in e], errors)

    def test_manifest_v2(self):
        self.check_module('mv2')

    def test_manifest_v3(self):
        self.check_module('mv3')


def versioned_add_on(name, version, version_name=None):
    """A Firefox add-on whose manifest has `version`, and `version_name` if
    given."""
    manifest = {
        'manifest_version': 2,
        'name': f'Firefox version {name} test add-on',
        'version': version,
        'browser_specific_settings': {'gecko': {'id': f'firefox-version-{name}@oganesson.test'}},
        'background': {'scripts': ['background.js']},
    }
    if version_name:
        manifest['version_name'] = version_name
    return {'manifest.json': json.dumps(manifest), 'background.js': 'self.started = true;'}


VERSIONED_ADD_ONS = {
    # Mozilla's re-signed builds, the most common suffix in the corpus.
    'resigned': versioned_add_on('resigned', '1.2resigned1'),
    # A suffix with more numbers after it, and the manifest's own version_name.
    'named': versioned_add_on('named', '1.3.4buildid20230720.091143', 'Release 1.3.4'),
}


class FirefoxVersionTest(BrowserTest):
    """Firefox's versions with a suffix: the add-on loads with the leading
    numbers as its version, the full string is its version name unless the
    manifest has one, and the add-on reads its manifest's version as it is."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-version-'))
        cls.unpacked = {}
        for name, files in VERSIONED_ADD_ONS.items():
            xpi = cls.folder / f'{name}.xpi'
            with zipfile.ZipFile(xpi, 'w') as archive:
                for file, text in files.items():
                    archive.writestr(file, text)
            cls.unpacked[name] = unpack_xpi(xpi, cls.folder / name)
        cls.browser_args = ('--load-extension=' + ','.join(str(f) for f in cls.unpacked.values()),)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def check_version(self, name, manifest_version, version, version_name):
        add_on = extension_id(self.unpacked[name])
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what=f'the {name} background')
            self.assertEqual(background.eval('browser.runtime.getManifest().version'), manifest_version)
            info = background.eval('browser.management.getSelf()')
        finally:
            background.close()
        self.assertEqual((info['version'], info['versionName']), (version, version_name))
        self.assertEqual(self.browser.extension_info(add_on)['version'], version_name)
        errors = self.browser.extension_errors(add_on)
        self.assertFalse([e for e in errors if 'version' in e], errors)

    def test_suffix(self):
        self.check_version('resigned', '1.2resigned1', '1.2', '1.2resigned1')

    def test_suffix_with_version_name(self):
        self.check_version('named', '1.3.4buildid20230720.091143', '1.3.4', 'Release 1.3.4')


LOCALE_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox locale test add-on',
        # A message the locale files don't have: Firefox keeps the text.
        'description': '__MSG_missing_description__',
        'version': '1',
        'default_locale': 'en',
        'browser_specific_settings': {'gecko': {'id': 'firefox-locale@oganesson.test'}},
        'background': {'scripts': ['background.js']},
    }),
    '_locales/en/messages.json': json.dumps({
        # A name with "-", as Tree Style Tab and Mozilla VPN have.
        'first-install-body': {'message': 'A dashed name'},
        # $HOST$ has no placeholder, as in User-Agent Switcher.
        'greeting': {'message': 'Hello $USER$ from $HOST$.',
                     'placeholders': {'user': {'content': 'you'}}},
    }),
    'background.js': 'self.started = true;',
}


class FirefoxLocaleTest(BrowserTest):
    """Locale files as Firefox reads them: a message name with "-", a
    placeholder that the message doesn't define, and an unknown message in
    the manifest. Chromium refuses to load such an add-on."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-locale-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in LOCALE_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_messages(self):
        background = self.browser.extension_background(extension_id(self.unpacked))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            self.assertEqual(background.eval("browser.i18n.getMessage('first-install-body')"),
                             'A dashed name')
            self.assertEqual(background.eval("browser.i18n.getMessage('greeting')"), 'Hello you from .')
            self.assertEqual(background.eval('browser.runtime.getManifest().description'),
                             '__MSG_missing_description__')
        finally:
            background.close()


SHORTCUTS_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox shortcuts test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-shortcuts@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        # Five shortcuts, one more than Chromium takes, each of a kind that
        # Chromium refuses, as Tab Stash, Tree Style Tab, Tridactyl and
        # Multi-Account Containers have them.
        'commands': {
            'ctrl-alt': {'suggested_key': {'default': 'Ctrl+Alt+Y'}, 'description': 'Ctrl+Alt'},
            'function-key': {'suggested_key': {'default': 'F9'}, 'description': 'F9'},
            'shift-function-key': {'suggested_key': {'default': 'Shift+F9'},
                                   'description': 'Shift+F9'},
            'mac-ctrl': {'suggested_key': {'default': 'MacCtrl+Shift+Y'},
                         'description': 'MacCtrl'},
            'no-description': {'suggested_key': {'default': 'Alt+Shift+5'}},
            # A key for another platform only, and no key at all.
            'mac-only': {'suggested_key': {'mac': 'Alt+Shift+M'}, 'description': 'Mac only'},
            'no-key': {},
        },
    }),
    'background.js': '''
        self.commands = [];
        browser.commands.onCommand.addListener(name => self.commands.push(name));
        self.started = true;
    ''',
}


class FirefoxShortcutsTest(BrowserTest):
    """Shortcuts as Firefox reads them: Ctrl+Alt, F1 to F12 alone or with
    Shift, MacCtrl as Ctrl, more than four shortcuts, and commands without a
    description or without a key for this platform. Chromium refuses to load
    such an add-on."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-shortcuts-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in SHORTCUTS_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_shortcuts(self):
        background = self.browser.extension_background(extension_id(self.unpacked))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            # Chromium's names, as its shortcuts page writes them: Alt+Ctrl.
            commands = background.eval(
                'browser.commands.getAll().then(all => all.map(c => [c.name, c.shortcut, c.description]))')
            self.assertEqual(sorted(commands), [
                ['ctrl-alt', 'Alt+Ctrl+Y', 'Ctrl+Alt'],
                ['function-key', 'F9', 'F9'],
                ['mac-ctrl', 'Ctrl+Shift+Y', 'MacCtrl'],
                ['mac-only', '', 'Mac only'],
                ['no-description', 'Alt+Shift+5', 'no-description'],
                ['no-key', '', 'no-key'],
                ['shift-function-key', 'Shift+F9', 'Shift+F9'],
            ])
            for keys, name in (('F9', 'function-key'), ('shift+F9', 'shift-function-key'),
                               ('ctrl+alt+y', 'ctrl-alt'), ('ctrl+shift+y', 'mac-ctrl')):
                self.browser.key(keys)
                wait_for(lambda name=name: background.eval(f'self.commands.includes({name!r})'),
                         what=f'the {name} command from {keys}')
        finally:
            background.close()

    def test_shortcuts_page(self):
        """chrome://extensions/shortcuts takes F1 to F12 alone, and Ctrl+Alt."""
        page = self.browser.new_tab('chrome://extensions/shortcuts')
        try:
            for description, keys, shortcut in (('no-key', 'F2', 'F2'),
                                                ('Mac only', 'ctrl+alt+u', 'Alt+Ctrl+U')):
                field = f"""(function find(root) {{
                    for (const node of root.querySelectorAll('*')) {{
                        if (node.localName === 'cr-shortcut-input' &&
                            node.inputAriaLabel.includes({description!r})) {{
                            return node;
                        }}
                        const inner = node.shadowRoot && find(node.shadowRoot);
                        if (inner) return inner;
                    }}
                    return null;
                }})(document)"""
                wait_for(lambda field=field: page.eval(f'!!{field}'), what=f'the {description} input')
                self.browser.key('shift')  # gives the window the input focus
                page.eval(f"{field}.shadowRoot.querySelector('#edit').click()")
                wait_for(lambda field=field: page.eval(
                    f"document.hasFocus() && {field}.shadowRoot.activeElement?.id === 'input'"),
                    what=f'the {description} input to take the focus')
                # At a high load, about 1 run in 100 loses the keystroke: no
                # key event reaches the page, which has the focus and still
                # waits for a key. Until it takes one, pressing again is safe.
                for _ in range(5):
                    self.browser.xdotool('key', keys)
                    try:
                        wait_for(lambda field=field: page.eval(f'{field}.readonly_'), timeout=2,
                                 what=f'the {description} input to take {keys}')
                        break
                    except AssertionError:
                        pass
                wait_for(lambda description=description, shortcut=shortcut: self.shortcut_of(
                    description) == shortcut, what=f'{shortcut} for {description}')
        finally:
            page.close()

    def shortcut_of(self, description):
        background = self.browser.extension_background(extension_id(self.unpacked))
        try:
            return background.eval(
                f'browser.commands.getAll().then(all => all.find(c => c.description == {description!r}).shortcut)')
        finally:
            background.close()


WEB_REQUEST_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox webRequest event page test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-web-request@oganesson.test'}},
        # An event page with a blocking webRequest listener, as AdGuard and
        # Ghostery have it.
        'background': {'scripts': ['background.js'], 'persistent': False},
        'permissions': ['webRequest', 'webRequestBlocking', 'http://127.0.0.1/*'],
    }),
    'background.js': '''
        self.blocked = [];
        browser.webRequest.onBeforeRequest.addListener(details => {
            self.blocked.push(new URL(details.url).pathname);
            return {cancel: true};
        }, {urls: ['http://127.0.0.1/blocked*']}, ['blocking']);
        self.started = true;
    ''',
}


class FirefoxWebRequestEventPageTest(BrowserTest):
    """A Manifest V2 event page that asks for webRequest: Chromium refuses to
    load it, Firefox runs it, and its blocking listener blocks a request.
    It runs as a persistent background page."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-web-request-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in WEB_REQUEST_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.server = Server({'/page': (200, {'Content-Type': 'text/html'}, b'<!doctype html><p>page'),
                             '/blocked': (200, {'Content-Type': 'text/plain'}, b'not blocked')})
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def test_blocking_listener(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        page = self.browser.new_tab(self.server.url('/page'))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            wait_for(lambda: page.eval("document.readyState == 'complete' && document.body.innerText"),
                     what='the page')
            result = page.eval("fetch('/blocked').then(r => r.text(), e => 'failed')")
            self.assertEqual(result, 'failed')
            self.assertEqual(background.eval('self.blocked'), ['/blocked'])
            self.assertNotIn('/blocked', self.server.requests)
        finally:
            background.close()
            self.browser.close_target(page)
        self.assertFalse(self.browser.extension_errors(add_on))


PAGE_ACTION_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox page action test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-page-action@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        # Both actions, as Multi-Account Containers and Sidebery have them.
        'browser_action': {'default_title': 'Toolbar', 'default_popup': 'toolbar.html'},
        'page_action': {'default_title': 'Page', 'default_popup': 'page.html'},
    }),
    'background.js': 'self.started = true;',
    'toolbar.html': '<!doctype html><p>toolbar',
    'page.html': '<!doctype html><p>page',
}

# Firefox's Manifest V3 has page actions; Chromium's doesn't.
PAGE_ACTION_V3_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 3,
        'name': 'Firefox Manifest V3 page action test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-page-action-v3@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'page_action': {'default_title': 'Page V3'},
    }),
    'background.js': 'self.started = true;',
}

# Each pageAction call on the active tab, then what each action holds.
PAGE_ACTION_CALLS = '''(async () => {
    const [tab] = await browser.tabs.query({active: true, lastFocusedWindow: true});
    const tabId = tab.id;
    const manifest = [await browser.pageAction.getTitle({tabId}),
                      await browser.pageAction.getPopup({tabId})];
    await browser.pageAction.show(tabId);
    await browser.pageAction.setTitle({tabId, title: 'Page for the tab'});
    await browser.pageAction.setPopup({tabId, popup: 'other.html'});
    await browser.pageAction.setIcon({tabId, imageData: new ImageData(16, 16)});
    await browser.pageAction.hide(tabId);
    return {
        manifest,
        page: [await browser.pageAction.getTitle({tabId}), await browser.pageAction.getPopup({tabId})],
        toolbar: [await browser.browserAction.getTitle({tabId}),
                  await browser.browserAction.getPopup({tabId})],
        onClicked: typeof browser.pageAction.onClicked.addListener,
    };
})()'''

PAGE_ACTION_TITLE = '''browser.tabs.query({active: true, lastFocusedWindow: true})
    .then(([tab]) => browser.pageAction.getTitle({tabId: tab.id}))'''


class FirefoxPageActionTest(BrowserTest):
    """page_action next to browser_action, which Chromium refuses to load, and
    page_action in Manifest V3: a second action that pageAction.* reaches, as
    in Firefox. What a tab sets is reset when the tab navigates."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-page-action-'))
        cls.unpacked = []
        for name, files in (('v2', PAGE_ACTION_ADD_ON), ('v3', PAGE_ACTION_V3_ADD_ON)):
            xpi = cls.folder / f'{name}.xpi'
            with zipfile.ZipFile(xpi, 'w') as archive:
                for file, text in files.items():
                    archive.writestr(file, text)
            cls.unpacked.append(unpack_xpi(xpi, cls.folder / name))
        cls.server = Server({'/one': (200, {'Content-Type': 'text/html'}, b'<!doctype html><p>one'),
                             '/two': (200, {'Content-Type': 'text/html'}, b'<!doctype html><p>two')})
        cls.browser_args = (f'--load-extension={",".join(map(str, cls.unpacked))}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def test_page_action(self):
        add_on = extension_id(self.unpacked[0])
        background = self.browser.extension_background(add_on)
        page = self.browser.new_tab(self.server.url('/one'))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            wait_for(lambda: page.eval("document.readyState == 'complete' && document.body.innerText"),
                     what='the page')
            result = background.eval(PAGE_ACTION_CALLS)
            base = f'chrome-extension://{add_on}/'
            self.assertEqual(result['manifest'], ['Page', base + 'page.html'])
            self.assertEqual(result['page'], ['Page for the tab', base + 'other.html'])
            self.assertEqual(result['toolbar'], ['Toolbar', base + 'toolbar.html'])
            self.assertEqual(result['onClicked'], 'function')
            page.eval(f"location.href = {json.dumps(self.server.url('/two'))}")
            wait_for(lambda: background.eval(PAGE_ACTION_TITLE) == 'Page',
                     what='the page action\'s title to reset')
        finally:
            background.close()
            self.browser.close_target(page)
        self.assertFalse(self.browser.extension_errors(add_on))

    def test_manifest_v3_page_action(self):
        add_on = extension_id(self.unpacked[1])
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            self.assertEqual(background.eval(PAGE_ACTION_TITLE), 'Page V3')
        finally:
            background.close()
        self.assertFalse(self.browser.extension_errors(add_on))


BROWSER_SETTINGS_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox browserSettings test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-browser-settings@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['browserSettings'],
        # The new tab page that newTabPageOverride gives.
        'chrome_url_overrides': {'newtab': 'newtab.html'},
    }),
    'background.js': '''
        // As Tab Stash listens, at startup.
        browser.browserSettings.homepageOverride.onChange.addListener(() => {});
        self.started = true;
    ''',
    'newtab.html': '<!doctype html><title>New tab</title>',
}

# Each setting's get(), then a set() and a clear() as gesture and zoom add-ons
# call them, and the value after them.
BROWSER_SETTINGS_CALLS = '''(async () => {
    const settings = {};
    for (const name of Object.keys(browser.browserSettings).sort()) {
        settings[name] = await browser.browserSettings[name].get({});
    }
    const results = [
        await browser.browserSettings.contextMenuShowEvent.set({value: 'mouseup'}),
        // A value only Firefox takes.
        await browser.browserSettings.overrideContentColorScheme.set({value: 'system'}),
        await browser.browserSettings.zoomSiteSpecific.clear({}),
    ];
    return {settings, results: results.map(result => result === undefined),
            after: (await browser.browserSettings.contextMenuShowEvent.get({})).value,
            verticalTabs: 'verticalTabs' in browser.browserSettings,
            warnings: await browser.management.getPermissionWarningsByManifest(JSON.stringify(
                {manifest_version: 2, name: 'Warnings', version: '1',
                 permissions: ['browserSettings']}))};
})()'''


class FirefoxBrowserSettingsTest(BrowserTest):
    """Firefox's browserSettings, read-only: get() gives each setting's value
    in this browser, from its pref where it has one; set() and clear() change
    nothing and resolve without a value, which reads as Firefox's false."""
    prefs = {
        **DEVELOPER_MODE,
        'homepage': 'https://example.org/start',
        'homepage_is_newtabpage': False,
        'oganesson': {'tabs': {'link_position': 2}},  # At the end.
        'settings': {'a11y': {'animation_policy': 'once',
                              'requested_page_colors': 1}},  # Off.
        'profile': {'default_content_setting_values': {'notifications': 2}},  # Block.
    }

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-browser-settings-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in BROWSER_SETTINGS_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_browser_settings(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            result = background.eval(BROWSER_SETTINGS_CALLS)
        finally:
            background.close()
        values = {name: setting['value'] for name, setting in result['settings'].items()}
        self.assertEqual(values, {
            # From the prefs.
            'homepageOverride': 'https://example.org/start',
            'newTabPageOverride': f'chrome-extension://{add_on}/newtab.html',
            'newTabPosition': 'atEnd',
            'imageAnimationBehavior': 'once',
            'overrideDocumentColors': 'never',
            'webNotificationsDisabled': True,
            # What Chromium always does, on Linux.
            'allowPopupsForUserEvents': True,
            'cacheEnabled': True,
            'closeTabsByDoubleClick': False,
            'contextMenuShowEvent': 'mousedown',
            'ftpProtocolEnabled': False,
            'openBookmarksInNewTabs': False,
            'openSearchResultsInNewTabs': False,
            'openUrlbarResultsInNewTabs': False,
            'overrideContentColorScheme': 'auto',
            'useDocumentFonts': True,
            'zoomFullPage': True,
            'zoomSiteSpecific': True,
        })
        self.assertEqual({setting['levelOfControl'] for setting in result['settings'].values()},
                         {'not_controllable'})
        self.assertEqual(result['results'], [True, True, True])
        self.assertEqual(result['after'], 'mousedown')
        # Tree Style Tab checks for it: this browser has no equal.
        self.assertFalse(result['verticalTabs'])
        # The home page and another add-on's new tab page are no one's
        # business without a warning, as in Firefox.
        self.assertEqual(result['warnings'], ['Read and change user and device settings'])
        self.assertFalse(self.browser.extension_errors(add_on))



THEME_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox theme test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-theme@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        # As in Firefox, reading the theme needs no permission.
    }),
    'background.js': '''
        // As Save Screenshot and Playback Speed listen, at startup.
        self.updates = [];
        browser.theme.onUpdated.addListener(info => self.updates.push(info));
        self.started = true;
    ''',
}

# Firefox's colour keys that the theme gives.
THEME_COLORS = {
    'frame', 'frame_inactive', 'tab_background_text', 'tab_background_separator',
    'tab_selected', 'tab_text', 'toolbar', 'toolbar_text', 'toolbar_top_separator', 'icons',
    'toolbar_field', 'toolbar_field_text', 'toolbar_field_border', 'popup', 'popup_text',
    'popup_highlight', 'popup_highlight_text', 'sidebar', 'ntp_background', 'ntp_text',
}


def brightness(color):
    """The brightness, 0 to 1, of a colour as #rrggbb."""
    red, green, blue = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


class FirefoxThemeTest(BrowserTest):
    """Firefox's theme API, read-only: getCurrent() gives the colours of the
    browser's theme in Firefox's key names, for the last focused window or a
    given one, and onUpdated fires with the new colours when the browser
    switches from light to dark. Images and properties are null, as in
    Firefox's empty theme."""
    prefs = {**DEVELOPER_MODE, 'browser': {'theme': {'color_scheme2': 1}}}  # Light.

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-theme-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in THEME_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def set_dark(self, background, light_toolbar):
        """Switches the browser to dark, as the appearance settings' mode menu
        does, and waits for an onUpdated with another toolbar colour."""
        settings = self.browser.new_tab('chrome://settings/appearance')
        try:
            settings.eval('''(async () => {
                const {browserProxyFactory, ColorSchemeMode} = await import(
                    'chrome://resources/cr_components/customize_color_scheme_mode/' +
                    'customize_color_scheme_mode.mojom-webui.js');
                browserProxyFactory.getInstance().handler.setColorSchemeMode(
                    ColorSchemeMode.kDark);
            })()''')
            wait_for(lambda: background.eval(
                f'self.updates.some(u => u.theme.colors.toolbar !== {json.dumps(light_toolbar)})'),
                what='theme.onUpdated with the dark theme')
        finally:
            self.browser.close_target(settings)

    def test_theme(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            light = background.eval('''(async () => {
                const window = await browser.windows.getLastFocused();
                let error;
                await browser.theme.getCurrent(987654).catch(e => { error = e.message; });
                return {theme: await browser.theme.getCurrent(),
                        window: await browser.theme.getCurrent(window.id), error,
                        // Throws for a permission this browser doesn't know.
                        permission: await browser.permissions.contains({permissions: ['theme']}),
                        warnings: await browser.management.getPermissionWarningsByManifest(
                            JSON.stringify({manifest_version: 2, name: 'Warnings',
                                            version: '1', permissions: ['theme']}))};
            })()''')
            self.assertEqual(background.eval('self.updates'), [])
            self.set_dark(background, light['theme']['colors']['toolbar'])
            dark = background.eval('''(async () => ({
                theme: await browser.theme.getCurrent(), updates: self.updates}))()''')
        finally:
            background.close()

        colors = light['theme']['colors']
        self.assertEqual(set(colors), THEME_COLORS)
        for name, color in colors.items():
            self.assertRegex(color, r'^(#[0-9a-f]{6}|rgba\(\d+, \d+, \d+, [0-9.]+\))$', name)
        self.assertIsNone(light['theme']['images'])
        self.assertIsNone(light['theme']['properties'])
        self.assertEqual(light['window'], light['theme'])
        self.assertIn('987654', light['error'])
        # The permission that theme.update() needs is known, not granted here,
        # and warns of nothing, as in Firefox.
        self.assertFalse(light['permission'])
        self.assertEqual(light['warnings'], [])
        self.assertGreater(brightness(colors['toolbar']), 0.6)
        self.assertLess(brightness(colors['toolbar_text']), 0.4)

        dark_colors = dark['theme']['colors']
        self.assertLess(brightness(dark_colors['toolbar']), 0.4)
        self.assertGreater(brightness(dark_colors['toolbar_text']), 0.6)
        self.assertLess(brightness(dark_colors['frame']), brightness(colors['frame']))
        # One update, with the new theme, for no window in particular.
        self.assertEqual(dark['updates'], [{'theme': dark['theme']}])
        self.assertFalse(self.browser.extension_errors(add_on))

if __name__ == '__main__':
    unittest.main()
