"""Firefox add-ons (dubna's webextensions/README.md): Firefox's WebExtensions
APIs that Chromium lacks, as an add-on from AMO calls them. One test per API,
each on the same small Manifest V2 add-on, as most of AMO's are. An add-on in
the profile's firefox_add_ons.named_firefox list is told it runs in Firefox."""

import hashlib
import io
import json
import shutil
import tempfile
import threading
import time
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

    def test_menus_is_context_menus(self):
        # The same object under both names. An add-on that reaches both, as
        # DuckDuckGo Privacy Essentials does, stopped at the second name.
        same = self.background_eval('''new Promise(done => {
            const same = browser.contextMenus === browser.menus && chrome.menus === browser.menus;
            setTimeout(() => done(same), 0);
        })''')
        self.assertTrue(same)

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
        # Firefox localizes it, as Tab Rotator's.
        'homepage_url': '__MSG_homepage__',
        'browser_specific_settings': {'gecko': {'id': 'firefox-locale@oganesson.test'}},
        'background': {'scripts': ['background.js']},
    }),
    '_locales/en/messages.json': json.dumps({
        # A name with "-", as Tree Style Tab and Mozilla VPN have.
        'first-install-body': {'message': 'A dashed name'},
        # $HOST$ has no placeholder, as in User-Agent Switcher.
        'greeting': {'message': 'Hello $USER$ from $HOST$.',
                     'placeholders': {'user': {'content': 'you'}}},
        'homepage': {'message': 'https://example.org/firefox-locale'},
    }),
    'background.js': 'self.started = true;',
}


class FirefoxLocaleTest(BrowserTest):
    """Locale files as Firefox reads them: a message name with "-", a
    placeholder that the message doesn't define, an unknown message in the
    manifest, and a message in homepage_url. Chromium refuses to load such an
    add-on."""

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

    def test_homepage_url(self):
        background = self.browser.extension_background(extension_id(self.unpacked))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            self.assertEqual(background.eval('browser.runtime.getManifest().homepage_url'),
                             'https://example.org/firefox-locale')
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


SCRIPTING_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox scripting test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-scripting@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        # Firefox gives scripting to Manifest V2 too (Privacy Badger, Ghostery).
        'permissions': ['scripting', 'http://127.0.0.1/*'],
    }),
    'background.js': 'self.started = true;',
    'content.js': 'document.documentElement.dataset.registered = "yes";',
}


class FirefoxScriptingTest(BrowserTest):
    """A Manifest V2 add-on with the scripting permission: Chromium leaves
    browser.scripting out, Firefox has it. The add-on runs a script in a page
    and registers a content script that runs on the next page."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-scripting-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in SCRIPTING_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.server = Server({'/one': (200, {'Content-Type': 'text/html'}, b'<!doctype html><p>one'),
                             '/two': (200, {'Content-Type': 'text/html'}, b'<!doctype html><p>two')})
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def test_scripting(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        one = self.browser.new_tab(self.server.url('/one'))
        two = None
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            # A new tab starts on about:blank: wait for the page itself.
            wait_for(lambda: one.eval("location.pathname == '/one' && document.readyState == 'complete'"),
                     what='the first page')
            result = background.eval('''(async () => {
                const [tab] = await browser.tabs.query({url: 'http://127.0.0.1/one'});
                const [injected] = await browser.scripting.executeScript(
                    {target: {tabId: tab.id}, func: () => document.body.innerText});
                await browser.scripting.registerContentScripts([{
                    id: 'registered', matches: ['http://127.0.0.1/two'], js: ['content.js'],
                    runAt: 'document_start'}]);
                const registered = await browser.scripting.getRegisteredContentScripts();
                return {injected: injected.result, registered: registered.map(script => script.id)};
            })()''')
            self.assertEqual(result, {'injected': 'one', 'registered': ['registered']})
            two = self.browser.new_tab(self.server.url('/two'))
            wait_for(lambda: two.eval("location.pathname == '/two' && document.readyState == 'complete'"),
                     what='the second page')
            self.assertEqual(two.eval('document.documentElement.dataset.registered'), 'yes')
            remaining = background.eval('''(async () => {
                await browser.scripting.unregisterContentScripts({ids: ['registered']});
                return (await browser.scripting.getRegisteredContentScripts()).length;
            })()''')
            self.assertEqual(remaining, 0)
        finally:
            background.close()
            self.browser.close_target(one)
            if two:
                self.browser.close_target(two)
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
        # The last update carries the new theme, for no window in particular.
        # The session's first notice of the system's theme (a caret blink rate,
        # an accent colour) may give one with the light theme before it.
        self.assertEqual(dark['updates'][-1], {'theme': dark['theme']})
        for update in dark['updates'][:-1]:
            self.assertEqual(update, {'theme': light['theme']})
        self.assertFalse(self.browser.extension_errors(add_on))


BADGE_TEXT_COLOR_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox badge text colour test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-badge-text-color@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'browser_action': {'default_title': 'Badge'},
    }),
    # As Mino and Ahrefs do when they start.
    'background.js': '''
        browser.browserAction.setBadgeText({text: "3"});
        browser.browserAction.setBadgeTextColor({color: "#ffffff"});
        self.started = true;
    ''',
}


class FirefoxBadgeTextColorTest(BrowserTest):
    """A Manifest V2 add-on sets and reads its badge's text colour, for every
    tab and for one, and reads whether its button is on the toolbar: Firefox's
    browserAction has the functions that Chromium gives only to action."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-badge-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in BADGE_TEXT_COLOR_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_badge_text_color(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            result = background.eval('''(async () => {
                const [tab] = await browser.tabs.query({active: true, lastFocusedWindow: true});
                const all = await browser.browserAction.getBadgeTextColor({});
                await browser.browserAction.setBadgeTextColor({color: [0, 0, 255, 255], tabId: tab.id});
                let error;
                await browser.browserAction.setBadgeTextColor({color: [0, 0, 0, 0]})
                    .catch(e => { error = e.message; });
                return {all, tab: await browser.browserAction.getBadgeTextColor({tabId: tab.id}),
                        still: await browser.browserAction.getBadgeTextColor({}), error,
                        settings: await browser.browserAction.getUserSettings()};
            })()''')
        finally:
            background.close()
        self.assertEqual(result['all'], [255, 255, 255, 255])
        self.assertEqual(result['tab'], [0, 0, 255, 255])
        self.assertEqual(result['still'], [255, 255, 255, 255])
        # A transparent colour is refused, as action's is.
        self.assertTrue(result['error'])
        # An unpacked add-on starts off the toolbar, in its menu.
        self.assertEqual(result['settings'], {'isOnToolbar': False})
        self.assertFalse(self.browser.extension_errors(add_on))


PEER_CONNECTION_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox peerConnectionEnabled test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-peer-connection@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['privacy'],
    }),
    'background.js': '''
        // As Happy Bonobo Disable WebRTC does, at startup.
        (async () => {
            try {
                self.setResult = await browser.privacy.network.peerConnectionEnabled.set({value: false});
            } catch (error) {
                self.error = error.message;
            }
            self.started = true;
        })();
    ''',
}


class FirefoxPeerConnectionTest(BrowserTest):
    """Firefox's privacy.network.peerConnectionEnabled, read-only: get() gives
    true, and set() and clear() change nothing and resolve without a value."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-peer-connection-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in PEER_CONNECTION_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_peer_connection_enabled(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            result = background.eval('''(async () => {
                const setting = browser.privacy.network.peerConnectionEnabled;
                return {error: self.error ?? null, set: self.setResult === undefined,
                        get: await setting.get({}),
                        clear: (await setting.clear({})) === undefined};
            })()''')
        finally:
            background.close()
        self.assertEqual(result, {'error': None, 'set': True, 'clear': True,
                                  'get': {'value': True, 'levelOfControl': 'not_controllable'}})
        self.assertFalse(self.browser.extension_errors(add_on))


CONTENT_SCRIPTS_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox contentScripts test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-content-scripts@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['scripting', 'http://127.0.0.1/*'],
    }),
    'background.js': 'self.started = true;',
    'content.js': 'document.documentElement.dataset.file = "yes";',
    'scripting.js': 'document.documentElement.dataset.scripting = "yes";',
    # A page in a folder: its files are relative to it, as in Firefox.
    'pages/page.html': '<!doctype html><title>Firefox contentScripts test page</title>',
    'pages/mark.js': 'document.documentElement.dataset.page = "yes";',
}

# What a page shows of each script: its marks, and the colour the CSS gives.
MARKS = '''({file: document.documentElement.dataset.file ?? null,
            code: document.documentElement.dataset.code ?? null,
            main: window.mainWorld ?? null,
            page: document.documentElement.dataset.page ?? null,
            color: getComputedStyle(document.body).color})'''
NO_MARKS = {'file': None, 'code': None, 'main': None, 'page': None, 'color': 'rgb(0, 0, 0)'}


class FirefoxContentScriptsTest(BrowserTest):
    """Firefox's contentScripts.register(): files (relative to the page that
    registers them) and code, JavaScript and CSS, in the isolated and the main
    world, until the object it resolves to is unregistered, or the page that
    registered them closes. The scripting API neither lists nor removes them,
    and updates its own scripts next to them."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-content-scripts-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in CONTENT_SCRIPTS_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        page = (200, {'Content-Type': 'text/html'}, b'<!doctype html><body>page')
        cls.server = Server({'/page': page, '/excluded': page})
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def marks(self, path):
        """Loads `path` in a new tab and returns its marks."""
        tab = self.browser.new_tab(self.server.url(path))
        try:
            wait_for(lambda: tab.eval(f"location.pathname == '{path}' && "
                                      "document.readyState == 'complete'"), what=path)
            return tab.eval(MARKS)
        finally:
            self.browser.close_target(tab)

    def test_register_and_unregister(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            result = background.eval('''(async () => {
                self.isolated = await browser.contentScripts.register({
                    matches: ['http://127.0.0.1/*'], excludeMatches: ['http://127.0.0.1/excluded'],
                    js: [{file: 'content.js'},
                         {code: 'document.documentElement.dataset.code = "yes";'}],
                    css: [{code: 'body { color: rgb(0, 128, 0); }'}], runAt: 'document_start'});
                self.main = await browser.contentScripts.register({
                    matches: ['http://127.0.0.1/*'], js: [{code: 'window.mainWorld = "yes";'}],
                    world: 'MAIN'});
                await browser.scripting.registerContentScripts([{
                    id: 'scripting', matches: ['http://127.0.0.1/*'], js: ['scripting.js']}]);
                // It describes every script it has, contentScripts' code too.
                await browser.scripting.updateContentScripts([{
                    id: 'scripting', runAt: 'document_end'}]);
                const listed = (await browser.scripting.getRegisteredContentScripts())
                    .map(script => script.id);
                // Without IDs: all of the scripting API's, none of contentScripts'.
                await browser.scripting.unregisterContentScripts();
                // Add-ons have no containers yet: Firefox's error for an unknown one.
                const container = await browser.contentScripts.register({
                    matches: ['http://127.0.0.1/*'], js: [{code: 'self.container = true;'}],
                    cookieStoreId: 'firefox-container-1'}).then(() => null, error => error.message);
                return {unregister: typeof self.isolated.unregister, listed, container,
                        left: (await browser.scripting.getRegisteredContentScripts()).length};
            })()''')
            self.assertEqual(result, {'unregister': 'function', 'listed': ['scripting'],
                                      'container': 'Invalid cookieStoreId', 'left': 0})
            self.assertEqual(self.marks('/page'), {**NO_MARKS, 'file': 'yes', 'code': 'yes',
                                                   'main': 'yes', 'color': 'rgb(0, 128, 0)'})
            self.assertEqual(self.marks('/excluded'), {**NO_MARKS, 'main': 'yes'})
            result = background.eval('''(async () => {
                await self.isolated.unregister();
                await self.main.unregister();
                return await self.isolated.unregister().then(() => null, error => error.message);
            })()''')
            # Firefox's message for an object unregistered twice.
            self.assertEqual(result, 'Content script already unregistered')
            self.assertEqual(self.marks('/page'), NO_MARKS)
        finally:
            background.close()
        self.assertFalse(self.browser.extension_errors(add_on))

    def test_closed_page_unregisters(self):
        add_on = extension_id(self.unpacked)
        page = self.browser.new_tab(f'chrome-extension://{add_on}/pages/page.html')
        try:
            # A new tab starts on about:blank: wait for the page itself.
            wait_for(lambda: page.eval("location.pathname == '/pages/page.html' && "
                                       "document.readyState == 'complete'"), what='the add-on page')
            # pages/mark.js: the file is relative to the page.
            page.eval('''browser.contentScripts.register({
                matches: ['http://127.0.0.1/*'], js: [{file: 'mark.js'}]}).then(() => true)''')
            self.assertEqual(self.marks('/page'), {**NO_MARKS, 'page': 'yes'})
        finally:
            self.browser.close_target(page)
        # Firefox unregisters a page's scripts when the page closes.
        wait_for(lambda: self.marks('/page') == NO_MARKS, what='the scripts to go with the page')
        self.assertFalse(self.browser.extension_errors(add_on))


DNR_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 3,
        'name': 'Firefox declarative_net_request test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-dnr@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        # Rules, but neither declarativeNetRequest permission, as DeepL and
        # Trend Micro's toolbar have them.
        'permissions': ['webRequest', 'webRequestBlocking'],
        'host_permissions': ['http://127.0.0.1/*'],
        'declarative_net_request': {
            'rule_resources': [{'id': 'rules', 'enabled': True, 'path': 'rules.json'}]},
    }),
    'rules.json': json.dumps([{'id': 1, 'priority': 1, 'action': {'type': 'block'},
                               'condition': {'urlFilter': '/blocked'}}]),
    'background.js': 'self.started = true;',
}


class FirefoxDeclarativeNetRequestTest(BrowserTest):
    """A Manifest V3 add-on with declarative_net_request rules and no
    declarativeNetRequest permission: Chromium refuses to load it, Firefox
    loads it without its rules."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-dnr-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in DNR_ADD_ON.items():
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

    def test_rules_without_permission(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        page = self.browser.new_tab(self.server.url('/page'))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            self.assertIsNone(background.eval('browser.declarativeNetRequest ?? null'))
            wait_for(lambda: page.eval("document.readyState == 'complete' && document.body.innerText"),
                     what='the page')
            result = page.eval("fetch('/blocked').then(r => r.text(), e => 'failed')")
            self.assertEqual(result, 'not blocked')
        finally:
            background.close()
            self.browser.close_target(page)
        self.assertFalse(self.browser.extension_errors(add_on))


def loading_tab_add_on(gecko_id):
    """An add-on that records the URL of each activated tab, as ColorfulTabs
    reads it; a Chrome Web Store extension without `gecko_id`."""
    manifest = {
        'manifest_version': 2,
        'name': f'Loading tab test add-on {gecko_id}',
        'version': '1',
        'background': {'scripts': ['background.js']},
        'permissions': ['tabs'],
    }
    if gecko_id:
        manifest['browser_specific_settings'] = {'gecko': {'id': gecko_id}}
    return {
        'manifest.json': json.dumps(manifest),
        'background.js': '''
            self.urls = [];
            browser.tabs.onActivated.addListener(async ({tabId}) => {
                self.urls.push((await chrome.tabs.get(tabId)).url);
            });
            self.started = true;
        ''',
    }


class FirefoxLoadingTabTest(BrowserTest):
    """A tab that hasn't committed its first navigation has the URL
    about:blank for a Firefox add-on, as in Firefox. Chromium gives it "",
    which new URL() refuses, and still does to a Chrome Web Store
    extension."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-loading-tab-'))
        cls.unpacked = {}
        for name, gecko_id in (('firefox', 'firefox-loading-tab@oganesson.test'), ('chrome', None)):
            xpi = cls.folder / f'{name}.xpi'
            with zipfile.ZipFile(xpi, 'w') as archive:
                for file, text in loading_tab_add_on(gecko_id).items():
                    archive.writestr(file, text)
            cls.unpacked[name] = unpack_xpi(xpi, cls.folder / name)
        cls.answer = threading.Event()

        def slow(_headers):
            cls.answer.wait(15)
            return 200, {'Content-Type': 'text/html'}, b'<!doctype html><p>slow'

        cls.server = Server({'/slow': slow})
        cls.browser_args = ('--load-extension=' + ','.join(str(f) for f in cls.unpacked.values()),)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.answer.set()
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def test_loading_tab_url(self):
        firefox = self.browser.extension_background(extension_id(self.unpacked['firefox']))
        chrome = self.browser.extension_background(extension_id(self.unpacked['chrome']))
        slow = self.server.url('/slow')
        try:
            for background in (firefox, chrome):
                wait_for(lambda b=background: b.eval('self.started === true'),
                         what='the background script')
            # The server holds the page, so the tab stays on its first navigation.
            created = firefox.eval(f'''browser.tabs.create({{url: '{slow}'}})
                .then(tab => [tab.url, tab.pendingUrl, new URL(tab.url).href])''')
            for background in (firefox, chrome):
                wait_for(lambda b=background: b.eval('self.urls.length') > 0,
                         what='tabs.onActivated')
            self.assertEqual(created, ['about:blank', slow, 'about:blank'])
            self.assertEqual(firefox.eval('self.urls'), ['about:blank'])
            self.assertEqual(chrome.eval('self.urls'), [''])
            self.answer.set()
            wait_for(lambda: firefox.eval(f'''browser.tabs.query({{url: '{slow}'}})
                .then(tabs => tabs.length)''') == 1, what='the page')
        finally:
            self.answer.set()
            firefox.close()
            chrome.close()
        self.assertFalse(self.browser.extension_errors(extension_id(self.unpacked['firefox'])))


def window_action_add_on(manifest_version):
    """An add-on that sets its action's values per window, as Save Screenshot
    (browserAction, Manifest V2) and Cookie Auto Decline (action, Manifest V3)
    do."""
    key = 'browser_action' if manifest_version == 2 else 'action'
    return {
        'manifest.json': json.dumps({
            'manifest_version': manifest_version,
            'name': f'Firefox window action test add-on {manifest_version}',
            'version': '1',
            'browser_specific_settings': {
                'gecko': {'id': f'firefox-window-action-{manifest_version}@oganesson.test'}},
            'background': {'scripts': ['background.js']},
            key: {'default_title': 'Default'},
        }),
        'background.js': 'self.started = true;',
        'page.html': '<!doctype html><p>A page',
    }


WINDOW_ACTION_ADD_ONS = {'mv2': window_action_add_on(2), 'mv3': window_action_add_on(3)}

# Two tabs of one window, one with its own title, and a tab of another window.
WINDOW_ACTION_CALLS = '''(async () => {
    const api = browser.browserAction || browser.action;
    const window1 = await browser.windows.getLastFocused();
    const [tab1] = await browser.tabs.query({active: true, windowId: window1.id});
    const own = await browser.tabs.create({windowId: window1.id, url: 'about:blank', active: false});
    const window2 = await browser.windows.create({url: 'about:blank'});
    const tab2 = window2.tabs[0];
    await api.setTitle({title: 'Global'});
    await api.setTitle({title: 'Window', windowId: window1.id});
    await api.setTitle({title: 'Own', tabId: own.id});
    await api.setBadgeText({text: 'W', windowId: window1.id});
    await api.setIcon({imageData: new ImageData(16, 16), windowId: window1.id});
    // setIcon goes through a binding of its own, which must pass windowId on.
    // Its promise never rejects, for Chromium's own errors too, so its errors
    // are read from runtime.lastError.
    const chromeApi = chrome.browserAction || chrome.action;
    const iconError = details => new Promise(resolve => chromeApi.setIcon(
        {imageData: new ImageData(16, 16), ...details},
        () => resolve(chrome.runtime.lastError?.message ?? null)));
    const errors = [];
    for (const details of [{tabId: tab1.id, windowId: window1.id}, {windowId: 2147483647}]) {
        await api.setTitle({title: 'Wrong', ...details})
            .then(() => errors.push(null), e => errors.push(e.message));
    }
    for (const details of [{tabId: tab1.id, windowId: window1.id}, {windowId: 2147483647}]) {
        errors.push(await iconError(details));
    }
    const title = details => api.getTitle(details);
    const badge = details => api.getBadgeText(details);
    const result = {
        titles: [await title({tabId: tab1.id}), await title({tabId: own.id}),
                 await title({tabId: tab2.id}), await title({windowId: window1.id}),
                 await title({windowId: window2.id}), await title({})],
        badges: [await badge({tabId: tab1.id}), await badge({tabId: tab2.id})],
        errors,
    };
    // A navigation resets a tab's own values, not its window's.
    const loaded = new Promise(resolve => browser.tabs.onUpdated.addListener(
        function done(id, change) {
            if (id === own.id && change.status === 'complete') {
                browser.tabs.onUpdated.removeListener(done);
                resolve();
            }
        }));
    await browser.tabs.update(own.id, {url: browser.runtime.getURL('page.html')});
    await loaded;
    result.navigated = await title({tabId: own.id});
    // windows.WINDOW_ID_CURRENT: the last focused window, for a background page.
    await api.setTitle({title: 'Current', windowId: browser.windows.WINDOW_ID_CURRENT});
    const current = await browser.windows.getCurrent();
    result.current = [await title({windowId: current.id}),
                      await title({windowId: browser.windows.WINDOW_ID_CURRENT}), await title({})];
    await browser.windows.remove(window2.id);
    await browser.tabs.remove(own.id);
    return result;
})()'''


class FirefoxWindowActionTest(BrowserTest):
    """browserAction's and action's setters and getters take Firefox's
    windowId: a value for the tabs of one window, under a tab's own value
    and over the global one. Chromium's schemas refused the key."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-window-action-'))
        cls.unpacked = {}
        for name, files in WINDOW_ACTION_ADD_ONS.items():
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

    def check(self, name):
        add_on = extension_id(self.unpacked[name])
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            result = background.eval(WINDOW_ACTION_CALLS)
        finally:
            background.close()
        self.assertEqual(result['titles'], ['Window', 'Own', 'Global', 'Window', 'Global', 'Global'])
        self.assertEqual(result['badges'], ['W', ''])
        self.assertEqual(result['errors'], ['Only one of tabId and windowId can be specified.',
                                            'Invalid window ID: 2147483647'] * 2)
        self.assertEqual(result['navigated'], 'Window')
        self.assertEqual(result['current'], ['Current', 'Current', 'Global'])
        self.assertFalse(self.browser.extension_errors(add_on))

    def test_browser_action(self):
        self.check('mv2')

    def test_action(self):
        self.check('mv3')


CONTEXTUAL_IDENTITIES_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox contextualIdentities test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-identities@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['contextualIdentities', 'cookies', 'tabs', 'http://127.0.0.1/*'],
    }),
    'background.js': '''
        self.events = [];
        for (const name of ['onCreated', 'onUpdated', 'onRemoved']) {
            browser.contextualIdentities[name].addListener(
                ({contextualIdentity: c}) => self.events.push([name, c.cookieStoreId, c.name]));
        }
        self.started = true;
    ''',
}

CONTEXTUAL_IDENTITIES_CALLS = '''(async () => {
    const error = p => p.then(() => null, e => e.message);
    return {
        all: await browser.contextualIdentities.query({}),
        named: await browser.contextualIdentities.query({name: 'Work'}),
        work: await browser.contextualIdentities.get('firefox-container-work'),
        errors: [await error(browser.contextualIdentities.get('firefox-container-none')),
                 await error(browser.contextualIdentities.get('firefox-default'))],
        // The cookies API takes Firefox's IDs of its two stores.
        cookies: [await error(browser.cookies.getAll({storeId: 'firefox-default'})),
                  await error(browser.cookies.getAll({storeId: 'firefox-private'}))],
    };
})()'''


class FirefoxContextualIdentitiesTest(BrowserTest):
    """Firefox's contextualIdentities, the read side: query() and get() give
    the browser's containers in Firefox's shape, the events follow the user's
    list, and tabs carry Firefox's cookieStoreId."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-identities-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in CONTEXTUAL_IDENTITIES_ADD_ON.items():
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

    def settings_eval(self, js):
        page = self.browser.new_tab('chrome://settings/containers')
        try:
            wait_for(lambda: page.eval('!!chrome.settingsPrivate'), what='Settings')
            return page.eval(js)
        finally:
            self.browser.close_target(page)

    def set_pref(self, name, value):
        self.settings_eval(f'chrome.settingsPrivate.setPref({json.dumps(name)}, {json.dumps(value)})')

    def test_query_get_and_events(self):
        result = self.background_eval(CONTEXTUAL_IDENTITIES_CALLS)
        self.assertEqual([c['cookieStoreId'] for c in result['all']],
                         ['firefox-container-personal', 'firefox-container-work',
                          'firefox-container-banking', 'firefox-container-shopping'])
        self.assertEqual(result['all'][0], {
            'name': 'Personal', 'icon': 'fingerprint',
            'iconUrl': 'resource://usercontext-content/fingerprint.svg',
            'color': 'blue', 'colorCode': '#37adff',
            'cookieStoreId': 'firefox-container-personal'})
        self.assertEqual(result['named'], [result['work']])
        self.assertEqual(result['work']['colorCode'], '#ff9f00')
        self.assertEqual(result['errors'], ['Invalid contextual identity: firefox-container-none',
                                            'Invalid contextual identity: firefox-default'])
        # The add-on may not reach incognito windows, as in Chromium.
        self.assertEqual(result['cookies'],
                         [None, 'Invalid cookie store id: "firefox-private".'])

        original = self.settings_eval(
            "chrome.settingsPrivate.getPref('containers.list').then(p => p.value)")
        changed = [dict(c, name='Job') if c['id'] == 'work' else c
                   for c in original if c['id'] != 'shopping']
        changed.append({'id': 'test', 'name': 'Test', 'icon': 'tree', 'color': 'green'})
        self.set_pref('containers.list', changed)
        try:
            events = wait_for(lambda: (lambda e: len(e) >= 3 and e)(
                self.background_eval('self.events')), what='the three events')
            self.assertEqual(self.background_eval(
                "browser.contextualIdentities.get('firefox-container-test').then(c => c.colorCode)"),
                '#51cd00')
        finally:
            self.set_pref('containers.list', original)
        # Putting the list back gives the three events the other way round,
        # and none fires twice.
        events = wait_for(lambda: (lambda e: len(e) >= 6 and e)(
            self.background_eval('self.events')), what='the events of putting the list back')
        self.assertEqual(sorted(events[:3]), [['onCreated', 'firefox-container-test', 'Test'],
                                              ['onRemoved', 'firefox-container-shopping', 'Shopping'],
                                              ['onUpdated', 'firefox-container-work', 'Job']])
        self.assertEqual(sorted(events[3:]), [['onCreated', 'firefox-container-shopping', 'Shopping'],
                                              ['onRemoved', 'firefox-container-test', 'Test'],
                                              ['onUpdated', 'firefox-container-work', 'Work']])
        self.assertFalse(self.browser.extension_errors(extension_id(self.unpacked)))

    def test_tab_cookie_store_id(self):
        tabs = 'browser.tabs.query({}).then(t => t.map(t => [t.id, t.cookieStoreId]))'
        before = dict(self.background_eval(tabs))
        self.set_pref('containers.new_tab', 'work')
        try:
            self.browser.key('ctrl+t')
            after = wait_for(lambda: (lambda t: len(t) > len(before) and t)(
                dict(self.background_eval(tabs))), what='the new tab')
        finally:
            self.set_pref('containers.new_tab', '')
        self.assertEqual(set(before.values()), {'firefox-default'})
        self.assertEqual({store for tab, store in after.items() if tab not in before},
                         {'firefox-container-work'})



# In a new incognito window: its tab's cookieStoreId, and the cookies API on
# firefox-private and on an ID that is no store.
PRIVATE_STORE_CALLS = '''(async () => {
    if (!await browser.extension.isAllowedIncognitoAccess()) {
        return null;
    }
    const error = p => p.then(() => null, e => e.message);
    const window = await browser.windows.create({incognito: true, url: 'about:blank'});
    const [tab] = await browser.tabs.query({windowId: window.id});
    const result = {
        store: tab.cookieStoreId,
        cookies: [await error(browser.cookies.getAll({storeId: 'firefox-private'})),
                  await error(browser.cookies.getAll({storeId: 'firefox-none'}))],
    };
    await browser.windows.remove(window.id);
    return result;
})()'''


class FirefoxPrivateCookieStoreTest(BrowserTest):
    """With access to incognito windows, which the profile gives it from the
    start, an incognito tab's cookieStoreId is Firefox's firefox-private, and
    the cookies API takes it as Chromium's incognito store."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-private-store-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in CONTEXTUAL_IDENTITIES_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        cls.prefs = {'extensions': {'settings': {extension_id(cls.unpacked): {'incognito': True}}}}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_private_store(self):
        background = self.browser.extension_background(extension_id(self.unpacked))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            result = background.eval(PRIVATE_STORE_CALLS)
        finally:
            background.close()
        self.assertEqual(result, {'store': 'firefox-private',
                                  'cookies': [None, 'Invalid cookie store id: "firefox-none".']})


UPDATE_FILTER_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox tabs.onUpdated filter test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-update-filter@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['tabs', 'http://127.0.0.1/*'],
    }),
    # Each listener records the updates it gets: the tab's id and the changes.
    'background.js': '''
        self.calls = {};
        self.listen = (name, filter) => {
            self.calls[name] = [];
            const listener = (id, change) => self.calls[name].push([id, Object.keys(change)]);
            browser.tabs.onUpdated.addListener(listener, filter);
            return listener;
        };
        // A listener that removes one whose filter refuses every update, the
        // first time it runs: that one must not run for that update either.
        browser.tabs.onUpdated.addListener(function remover() {
            browser.tabs.onUpdated.removeListener(self.never);
            browser.tabs.onUpdated.removeListener(remover);
        });
        self.never = listen('never', {tabId: 2147483647});
        listen('all');
        listen('null', null);
        listen('nullParts', {properties: ['status'], windowId: null, urls: null});
        listen('status', {properties: ['status']});
        listen('title', {properties: ['title']});
        listen('hidden', {properties: ['hidden']});
        listen('urls', {urls: ['http://127.0.0.1/filtered*']});
        listen('default', {cookieStoreId: 'firefox-default'});
        listen('container', {cookieStoreId: 'firefox-container-work'});
        listen('noWindow', {windowId: 2147483647});
        // Patterns that don't parse here throw nothing, as in Firefox, and
        // match no URL: Firefox's own scheme among them.
        listen('badPatterns', {urls: ['not a pattern', 'moz-extension://*/*']});
        browser.tabs.onUpdated.removeListener(listen('removed', {properties: ['status']}));
        self.errors = [];
        // A getter that throws: its exception reaches the caller, and no
        // listener is registered.
        const throwing = {get tabId() { throw new Error('getter'); }};
        for (const [event, filter] of [[browser.tabs.onUpdated, 'filter'],
                                       [browser.tabs.onUpdated, []],
                                       [browser.tabs.onCreated, {}],
                                       [browser.tabs.onUpdated, {colour: 'red'}],
                                       [browser.tabs.onUpdated, {urls: 'http://127.0.0.1/*'}],
                                       [browser.tabs.onUpdated, {urls: []}],
                                       [browser.tabs.onUpdated, {urls: [1]}],
                                       [browser.tabs.onUpdated, {properties: ['colour']}],
                                       [browser.tabs.onUpdated, {tabId: '1'}],
                                       [browser.tabs.onUpdated, {cookieStoreId: 1}],
                                       [browser.tabs.onUpdated, throwing]]) {
            try {
                event.addListener(() => { self.refusedRan = true; }, filter);
                self.errors.push(null);
            } catch (e) {
                self.errors.push(e.message);
            }
        }
        self.started = true;
    ''',
}

# Opens a tab on `url`, with a listener for its id alone, and waits until it
# has loaded with its title.
UPDATE_FILTER_OPEN = '''(async url => {
    const tab = await browser.tabs.create({url: 'about:blank', active: false});
    self.listen('tab' + tab.id, {tabId: tab.id});
    const done = new Promise(resolve => browser.tabs.onUpdated.addListener(
        function loaded(id, change, updated) {
            if (id === tab.id && updated.status === 'complete' && updated.title === 'Titled') {
                browser.tabs.onUpdated.removeListener(loaded);
                resolve();
            }
        }));
    await browser.tabs.update(tab.id, {url});
    await done;
    return tab.id;
})'''


class FirefoxUpdateFilterTest(BrowserTest):
    """Firefox's filter of tabs.onUpdated: a listener runs only for the
    updates that match its urls, properties, tabId, windowId and
    cookieStoreId. Chromium threw "This event does not support filters"."""

    @classmethod
    def setUpClass(cls):
        page = (200, {'Content-Type': 'text/html'}, b'<!doctype html><title>Titled</title><p>page')
        cls.server = Server({'/filtered': page, '/other': page})
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-update-filter-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in UPDATE_FILTER_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def test_filters(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            window = background.eval('browser.windows.getLastFocused().then(w => w.id)')
            background.eval(f"self.listen('window', {{windowId: {window}}})")
            urls = [json.dumps(self.server.url(path)) for path in ('/filtered', '/other')]
            filtered = background.eval(f'{UPDATE_FILTER_OPEN}({urls[0]})')
            other = background.eval(f'{UPDATE_FILTER_OPEN}({urls[1]})')
        finally:
            background.close()
        work = self.container_tab(add_on)
        background = self.browser.extension_background(add_on)
        try:
            calls = background.eval('self.calls')
            errors = background.eval('self.errors')
            refused_ran = background.eval('self.refusedRan === true')
            background.eval(f'browser.tabs.remove([{filtered}, {other}, {work}])')
        finally:
            background.close()

        def tabs(name):
            return {tab for tab, _ in calls[name]}

        def with_key(key):
            return [call for call in calls['all'] if key in call[1]]

        def refused(detail):
            return f'Type error for parameter filter ({detail}) for tabs.onUpdated.'

        self.assertEqual(errors, [
            'Incorrect argument types for tabs.onUpdated.',
            'Incorrect argument types for tabs.onUpdated.',
            'This event does not support filters',
            refused('Unexpected property "colour"'),
            refused('Error processing urls: Expected array'),
            refused('Error processing urls: Array requires at least 1 items; you have 0'),
            refused('Error processing urls.0: Expected string'),
            refused('Error processing properties.0: Invalid enumeration value "colour"'),
            refused('Error processing tabId: Expected integer'),
            refused('Error processing cookieStoreId: Expected string'),
            'getter'])
        self.assertFalse(refused_ran)
        self.assertTrue({filtered, other, work} <= tabs('all'))
        self.assertEqual(calls['null'], calls['all'])
        self.assertEqual(calls['nullParts'], calls['status'])
        self.assertTrue({filtered, other, work} <= tabs('window'))
        self.assertEqual(tabs('container'), {work})
        self.assertNotIn(work, tabs('default'))
        self.assertEqual(calls['default'], [c for c in calls['all'] if c[0] != work])
        self.assertTrue(with_key('status'))
        self.assertEqual(calls['status'], with_key('status'))
        self.assertTrue(with_key('title'))
        self.assertEqual(calls['title'], with_key('title'))
        self.assertEqual(tabs('urls'), {filtered})
        self.assertEqual(tabs(f'tab{filtered}'), {filtered})
        self.assertEqual(tabs(f'tab{other}'), {other})
        for name in ['hidden', 'removed', 'never', 'noWindow', 'badPatterns']:
            self.assertEqual(calls[name], [], name)
        self.assertFalse(self.browser.extension_errors(add_on))

    def container_tab(self, add_on):
        """Opens a tab in the Work container, as the user does, loads a page
        in it from the add-on, and returns its id."""
        def set_new_tab(container):
            page = self.browser.new_tab('chrome://settings/containers')
            try:
                wait_for(lambda: page.eval('!!chrome.settingsPrivate'), what='Settings')
                page.eval(f"chrome.settingsPrivate.setPref('containers.new_tab', '{container}')")
            finally:
                self.browser.close_target(page)

        background = self.browser.extension_background(add_on)
        try:
            before = set(background.eval('browser.tabs.query({}).then(t => t.map(t => t.id))'))
            set_new_tab('work')
            try:
                self.browser.key('ctrl+t')
                work = wait_for(lambda: next(iter(set(background.eval(
                    'browser.tabs.query({}).then(t => t.map(t => t.id))')) - before), None),
                    what='the new tab')
            finally:
                set_new_tab('')
            url = json.dumps(self.server.url('/other'))
            background.eval(f'''new Promise(resolve => {{
                browser.tabs.onUpdated.addListener(function loaded(id, change, tab) {{
                    if (id === {work} && tab.status === 'complete' && tab.title === 'Titled') {{
                        browser.tabs.onUpdated.removeListener(loaded);
                        resolve();
                    }}
                }});
                browser.tabs.update({work}, {{url: {url}}});
            }})''')
            return work
        finally:
            background.close()


PROXY_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox proxy test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-proxy@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        # In Firefox, * covers ws: and wss: too.
        'permissions': ['proxy', '*://*/*'],
    }),
    # self.port is the test's proxy. Each host stands for one kind of answer.
    'background.js': '''
        self.seen = [];
        self.filtered = [];
        self.typed = [];
        self.errors = [];
        self.refused = [];
        self.answer = details => {
            self.seen.push(details);
            const proxy = {type: 'http', host: '127.0.0.1', port: self.port};
            switch (new URL(details.url).hostname) {
                case 'proxied.test': return proxy;
                case 'promised.test': return Promise.resolve([{...proxy, port: String(self.port)}]);
                case 'refused.test': return {type: 'gopher', host: '127.0.0.1', port: self.port};
                case 'rejected.test': return Promise.reject(new Error('no proxy today'));
                case 'string.test': return 'DIRECT';
                case 'socket.test': return proxy;
                case 'kept.test': return proxy;
                case 'nulled.test': return proxy;
                case 'later.test': return proxy;
                case 'ended.test': return [proxy, null, {type: 'gopher'}];
                default: return {type: 'direct'};
            }
        };
        self.onlyPromised = details => { self.filtered.push(details.url); };
        // Asked after self.answer, and builds on its answer, as in Firefox:
        // a proxy replaces it, direct keeps it, null is a direct connection,
        // and one Firefox refuses changes nothing.
        self.last = details => {
            switch (new URL(details.url).hostname) {
                case 'last.test': return {type: 'http', host: '127.0.0.1', port: self.port};
                case 'kept.test': return {type: 'direct'};
                case 'nulled.test': return null;
                case 'later.test': return {type: 'gopher'};
            }
        };
        // A request's type, tab and window aren't known: they filter nothing.
        self.typedListener = details => { self.typed.push(details.url); };
        browser.proxy.onRequest.addListener(self.answer, {urls: ['*://*/*']}, ['requestHeaders']);
        browser.proxy.onRequest.addListener(self.onlyPromised, {urls: ['http://promised.test/*']});
        browser.proxy.onRequest.addListener(self.last, {urls: ['<all_urls>']});
        browser.proxy.onRequest.addListener(
            self.typedListener, {urls: ['<all_urls>'], types: ['main_frame'], tabId: 5, windowId: 1});
        for (const filter of [{}, {urls: []}, {urls: ['<all_urls>'], properties: ['title']},
                              {urls: ['<all_urls>'], incognito: 'no'}]) {
            try {
                browser.proxy.onRequest.addListener(() => {}, filter);
                self.refused.push(null);
            } catch (error) {
                self.refused.push(error.message);
            }
        }
        browser.proxy.onError.addListener(
            error => self.errors.push([error instanceof Error, error.message]));
        self.started = true;
    ''',
}

# What a fetch from the background gets: the page's text, or that it failed.
PROXY_FETCH = "(url => fetch(url).then(r => r.text(), error => 'failed: ' + error.name))"


def title(page):
    """The page's title, or None while it navigates."""
    try:
        return page.eval('document.title')
    except Exception:  # pylint: disable=broad-except
        return None


class FirefoxProxyTest(BrowserTest):
    """Firefox's proxy.onRequest and proxy.onError: listeners' answers, a
    ProxyInfo, a list of them, null or a promise of these, decide the proxy of
    a request, as far as their filters' URLs reach. Each answer builds on the
    one before, as in Firefox. An answer Firefox refuses, or a promise that
    rejects, goes to proxy.onError as an Error and changes nothing.
    WebSockets are asked about too, and a filter's types, tabId and windowId,
    which aren't known of a request, filter nothing. Without listeners,
    nothing is asked."""

    @classmethod
    def setUpClass(cls):
        # The proxy: the browser asks it for http://<host>/page, which it
        # answers by the path.
        cls.proxy = Server({
            '/page': (200, {'Content-Type': 'text/html'},
                      b'<!doctype html><title>Through the proxy</title>proxied'),
        })
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-proxy-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in PROXY_ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.proxy.stop()
        shutil.rmtree(cls.folder)

    def test_on_request(self):
        add_on = extension_id(self.unpacked)
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            background.eval(f'self.port = {self.proxy.port}')
            # A page in a tab.
            page = self.browser.new_tab('http://proxied.test/page')
            try:
                wait_for(lambda: title(page) == 'Through the proxy', timeout=30,
                         what='the page through the proxy')
            finally:
                self.browser.close_target(page)
            proxied_host = self.proxy.headers['/page']['Host']
            promised = background.eval(f'{PROXY_FETCH}("http://promised.test/page")')
            refused = background.eval(f'{PROXY_FETCH}("http://refused.test/page")')
            rejected = background.eval(f'{PROXY_FETCH}("http://rejected.test/page")')
            string = background.eval(f'{PROXY_FETCH}("http://string.test/page")')
            last = background.eval(f'{PROXY_FETCH}("http://last.test/page")')
            kept = background.eval(f'{PROXY_FETCH}("http://kept.test/page")')
            nulled = background.eval(f'{PROXY_FETCH}("http://nulled.test/page")')
            later = background.eval(f'{PROXY_FETCH}("http://later.test/page")')
            # A null in a list ends it: what follows isn't read.
            ended = background.eval(f'{PROXY_FETCH}("http://ended.test/page")')
            # The proxy doesn't speak WebSocket: only the question counts.
            background.eval('''new Promise(done => {
                const socket = new WebSocket('ws://socket.test/chat');
                socket.onerror = socket.onclose = () => done();
            })''')
            wait_for(lambda: len(background.eval('self.errors')) == 4, what='proxy.onError')
            seen = background.eval('self.seen')
            filtered = background.eval('self.filtered')
            errors = background.eval('self.errors')
            refused_filters = background.eval('self.refused')
            # The tab's favicon goes through the proxy too, whenever it loads.
            pages = self.proxy.requests.count('/page')
            # Without listeners, nothing is asked, and the request goes direct,
            # where .test names don't resolve.
            typed = background.eval('self.typed')
            background.eval('''
                browser.proxy.onRequest.removeListener(self.answer);
                browser.proxy.onRequest.removeListener(self.onlyPromised);
                browser.proxy.onRequest.removeListener(self.last);
                browser.proxy.onRequest.removeListener(self.typedListener);''')
            after = background.eval(f'{PROXY_FETCH}("http://proxied.test/page")')
            seen_after = background.eval('self.seen.length')
        finally:
            background.close()

        self.assertEqual(proxied_host, 'proxied.test')
        self.assertTrue(promised.endswith('</title>proxied'), promised)
        for text in (last, kept, later, ended):
            self.assertTrue(text.endswith('</title>proxied'), text)
        self.assertTrue(nulled.startswith('failed'), nulled)
        self.assertEqual(self.proxy.headers['/page']['Host'], 'ended.test')
        self.assertEqual(pages, 6)
        self.assertTrue(refused.startswith('failed'), refused)
        self.assertTrue(rejected.startswith('failed'), rejected)
        self.assertTrue(string.startswith('failed'), string)
        self.assertEqual(errors, [
            [True, 'ProxyInfoData: Invalid proxy server type: "gopher"'],
            [True, 'no proxy today'],
            [True, 'ProxyInfoData: proxyData must be an object or array of objects'],
            [True, 'ProxyInfoData: Invalid proxy server type: "gopher"']])
        self.assertIn('ws://socket.test/chat', [d['url'] for d in seen])
        self.assertIn('http://proxied.test/page', typed)
        self.assertEqual(filtered, ['http://promised.test/page'])
        first = next(d for d in seen if d['url'] == 'http://proxied.test/page')
        self.assertIsInstance(first.pop('requestId'), str)
        self.assertIsInstance(first.pop('timeStamp'), (int, float))
        self.assertEqual(first, {'url': 'http://proxied.test/page', 'type': 'other',
                                 'tabId': -1, 'frameId': -1, 'parentFrameId': -1,
                                 'incognito': False, 'thirdParty': False, 'fromCache': False,
                                 'cookieStoreId': 'firefox-default'})
        self.assertEqual(refused_filters, [
            'Type error for parameter filter (Property "urls" is required) for proxy.onRequest.',
            'Type error for parameter filter (Error processing urls: Array requires at least 1 '
            'items; you have 0) for proxy.onRequest.',
            'Type error for parameter filter (Unexpected property "properties") for '
            'proxy.onRequest.',
            'Type error for parameter filter (Error processing incognito: Expected boolean) for '
            'proxy.onRequest.'])
        self.assertTrue(after.startswith('failed'), after)
        self.assertEqual(seen_after, len(seen))
        self.assertEqual(self.proxy.requests.count('/page'), pages)
        self.assertFalse(self.browser.extension_errors(add_on))


GECKO_ID = 'gecko-id@oganesson.test'
PEER_GECKO_ID = '{6c3e1f0a-8b2d-4e5f-9a7b-1c2d3e4f5a6b}'
GECKO_ID_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Gecko ID test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': GECKO_ID}},
        'background': {'scripts': ['background.js']},
        'permissions': ['storage'],
    }),
    'background.js': 'self.started = true;',
}
# An add-on that answers others by message and by port, as DeArrow answers
# SponsorBlock.
GECKO_PEER_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Gecko ID peer test add-on',
        'version': '1',
        'applications': {'gecko': {'id': PEER_GECKO_ID}},
        'background': {'scripts': ['background.js']},
    }),
    'background.js': """
        browser.runtime.onMessageExternal.addListener((message, sender, respond) => {
            respond('pong ' + message);
        });
        browser.runtime.onConnectExternal.addListener(port => {
            port.onMessage.addListener(message => port.postMessage('pong ' + message));
        });
        self.started = true;
    """,
}
# The same, with a key, which gives its ID: it is reached by its Gecko ID all
# the same.
GECKO_KEYED_ADD_ON = {
    'manifest.json': json.dumps({
        **json.loads(GECKO_PEER_ADD_ON['manifest.json']),
        'name': 'Gecko ID keyed test add-on',
        'applications': {'gecko': {'id': 'keyed@oganesson.test'}},
        'key': ('MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDJnRbHexNTjRkPiiY/aArVJM+iKGwGLV6K7ivyrBfl1h'
                'wn8AjDF2aD2+1AsxJ2LeZL8z7FxJ7WPxJAoIyCfMOULQPV9LJ8Pq8egUMcC5YKvZN4rpIuEvLvWdAtwZ'
                'lcFj6K2+Tlq8b5NE5Aj3BJwfRQVHtfdYj92BuW9zflWZPMDwIDAQAB'),
    }),
    'background.js': GECKO_PEER_ADD_ON['background.js'],
}
GECKO_ID_CALLS = """(async () => {
    const error = async call => {
        try {
            await call();
            return null;
        } catch (e) {
            return e.message;
        }
    };
    return {
        message: await browser.runtime.sendMessage('%(peer)s', 'ping'),
        keyed: await browser.runtime.sendMessage('keyed@oganesson.test', 'ping'),
        port: await new Promise(done => {
            const port = browser.runtime.connect('%(peer)s');
            port.onMessage.addListener(done);
            port.postMessage('ping');
        }),
        absent: await error(() => browser.runtime.sendMessage('absent@oganesson.test', 'ping')),
        invalid: await error(() => browser.runtime.sendMessage('not an ID', 'ping')),
    };
})()""" % {'peer': PEER_GECKO_ID}


class FirefoxGeckoIdTest(BrowserTest):
    """An add-on takes its ID from its Gecko ID, so the same add-on loaded
    from another folder is the same extension, with its storage, and other
    add-ons reach it by its Gecko ID, as in Firefox."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-gecko-id-'))
        for name, files in (('first', GECKO_ID_ADD_ON), ('second', GECKO_ID_ADD_ON),
                            ('peer', GECKO_PEER_ADD_ON), ('keyed', GECKO_KEYED_ADD_ON)):
            (cls.folder / name).mkdir()
            for file, text in files.items():
                (cls.folder / name / file).write_text(text)
        cls.others = f'{cls.folder / "peer"},{cls.folder / "keyed"}'
        cls.browser_args = (f'--load-extension={cls.folder / "first"},{cls.others}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def started(self, folder):
        background = self.browser.extension_background(extension_id(folder))
        wait_for(lambda: background.eval('self.started === true'), what='the background script')
        return background

    def test_message_by_gecko_id(self):
        self.started(self.folder / 'peer').close()
        self.started(self.folder / 'keyed').close()
        background = self.started(self.folder / 'first')
        try:
            result = background.eval(GECKO_ID_CALLS)
        finally:
            background.close()
        self.assertEqual(result['message'], 'pong ping')
        self.assertEqual(result['port'], 'pong ping')
        self.assertEqual(result['keyed'], 'pong ping')
        self.assertIn('Receiving end does not exist', result['absent'])
        self.assertIn("Invalid extension id: 'not an ID'", result['invalid'])

    def test_reinstall_keeps_id_and_storage(self):
        # Not the ID of either folder's path.
        add_on = extension_id(self.folder / 'first')
        self.assertEqual(add_on, extension_id(self.folder / 'second'))
        background = self.started(self.folder / 'first')
        try:
            background.eval("browser.storage.local.set({kept: 'from the first folder'})")
        finally:
            background.close()
        self.browser.quit()
        self.browser.args = [arg for arg in self.browser.args
                             if not arg.startswith('--load-extension=')]
        self.browser.args.append(f'--load-extension={self.folder / "second"},{self.others}')
        self.browser.start()
        background = self.started(self.folder / 'second')
        try:
            stored = background.eval("browser.storage.local.get('kept')")
        finally:
            background.close()
        self.assertEqual(stored, {'kept': 'from the first folder'})
        self.assertTrue(self.browser.extension_info(add_on)['prettifiedPath']
                        .endswith('/second'))


class FirefoxGeckoIdOldInstallTest(BrowserTest):
    """An add-on with a Gecko ID installed unpacked before its ID came from
    the Gecko ID keeps the ID of its folder, and its storage with it."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-gecko-id-old-'))
        for file, text in GECKO_ID_ADD_ON.items():
            (cls.folder / file).write_text(text)
        cls.browser_args = (f'--load-extension={cls.folder}',)
        cls.prefs = DEVELOPER_MODE
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_old_install_keeps_its_id(self):
        gecko = extension_id(self.folder)
        self.browser.extension_background(gecko).close()
        self.browser.quit()
        # The install as an earlier version left it: unpacked (location 4),
        # under the ID of its folder.
        folder_id = hashlib.sha256(str(self.folder.resolve()).encode()).hexdigest()[:32].translate(
            str.maketrans('0123456789abcdef', 'abcdefghijklmnop'))
        preferences = self.browser.profile / 'Default/Preferences'
        prefs = json.loads(preferences.read_text())
        settings = prefs['extensions']['settings']
        settings[folder_id] = {**settings.pop(gecko), 'location': 4}
        preferences.write_text(json.dumps(prefs))
        self.browser.args = [arg for arg in self.browser.args
                             if not arg.startswith('--load-extension=')]
        self.browser.start()
        background = self.browser.extension_background(folder_id)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            background.eval("browser.storage.local.set({kept: 'before the reload'})")
            # A reload loads it from its folder again, as chrome://extensions'
            # Reload does. The page before it has the mark.
            background.eval('self.beforeReload = true; '
                            'setTimeout(() => browser.runtime.reload(), 100); true')
        finally:
            background.close()

        def reloaded():
            try:
                page = self.browser.extension_background(folder_id, timeout=1)
            except AssertionError:
                return None
            try:
                if page.eval('self.started === true && self.beforeReload !== true'):
                    return [page.eval("browser.storage.local.get('kept')")]
            except (OSError, AssertionError, RuntimeError):
                pass  # The page before the reload closed meanwhile.
            finally:
                page.close()
            return None

        stored = wait_for(reloaded, what='the reloaded background')[0]
        self.assertEqual(stored, {'kept': 'before the reload'})
        self.assertFalse([t for t in self.browser.targets() if gecko in t['url']])


BOOKMARK_IDS_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Bookmark IDs test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'bookmark-ids@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['bookmarks'],
    }),
    'background.js': 'self.started = true;',
}
# Each of Firefox's folder IDs that takes bookmarks, as Pouch saves into
# "unfiled_____": a bookmark created in it, then its folder's children read
# through it, and Chromium's folder that it is. Mobile bookmarks, which
# Chromium's desktop hides while the folder is empty, refuses a bookmark as
# Chromium's own ID for it does.
BOOKMARK_IDS_CALLS = """(async () => {
    const ids = ['toolbar_____', 'menu________', 'unfiled_____'];
    const created = {};
    for (const id of ids) {
        const bookmark = await browser.bookmarks.create(
            {parentId: id, title: id, url: 'https://example.com/' + id});
        created[id] = bookmark.id;
    }
    const [root] = await browser.bookmarks.getTree();
    const folders = Object.fromEntries(root.children.map(f => [f.id, f.folderType]));
    const read = {};
    for (const id of ids) {
        const [folder] = await browser.bookmarks.get(id);
        read[id] = {
            folder: folders[folder.id],
            children: (await browser.bookmarks.getChildren(id)).map(b => b.title),
            subTree: (await browser.bookmarks.getSubTree(id))[0].id === folder.id,
        };
    }
    const error = call => call.then(() => null, e => e.message);
    const moved = await browser.bookmarks.move(created['toolbar_____'], {parentId: 'unfiled_____'});
    return {
        read,
        root: (await browser.bookmarks.get('root________'))[0].id === root.id,
        moved: folders[moved.parentId],
        createdInRoot: await error(browser.bookmarks.create({parentId: 'root________', title: 'x'})),
        removeFolder: await error(browser.bookmarks.remove('menu________')),
        unknown: await error(browser.bookmarks.get('places______')),
        removed: await error(browser.bookmarks.remove(created['menu________'])),
        mobile: await error(browser.bookmarks.create(
            {parentId: 'mobile______', title: 'x', url: 'https://example.com/'})),
        chromiumMobile: await error(browser.bookmarks.create(
            {parentId: '3', title: 'x', url: 'https://example.com/'})),
    };
})()"""


class FirefoxBookmarkIdsTest(BrowserTest):
    """The bookmarks API takes Firefox's fixed folder IDs: "toolbar_____" is
    the bookmarks bar, "menu________" and "unfiled_____" Other bookmarks,
    "mobile______" Mobile bookmarks and "root________" the root."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-bookmark-ids-'))
        for file, text in BOOKMARK_IDS_ADD_ON.items():
            (cls.folder / file).write_text(text)
        cls.browser_args = (f'--load-extension={cls.folder}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_bookmark_ids(self):
        background = self.browser.extension_background(extension_id(self.folder))
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            result = background.eval(BOOKMARK_IDS_CALLS)
        finally:
            background.close()
        other = {'folder': 'other', 'children': ['menu________', 'unfiled_____'], 'subTree': True}
        self.assertEqual(result['read'], {
            'toolbar_____': {'folder': 'bookmarks-bar', 'children': ['toolbar_____'],
                             'subTree': True},
            'menu________': other,
            'unfiled_____': other,
        })
        self.assertTrue(result['root'])
        self.assertEqual(result['moved'], 'other')
        self.assertEqual(result['createdInRoot'], "Can't modify the root bookmark folders.")
        self.assertEqual(result['removeFolder'], "Can't modify the root bookmark folders.")
        self.assertEqual(result['unknown'], 'Bookmark id is invalid.')
        self.assertIsNone(result['removed'])
        self.assertEqual(result['mobile'], "Can't find parent bookmark for id.")
        self.assertEqual(result['chromiumMobile'], result['mobile'])
        self.assertFalse(self.browser.extension_errors(extension_id(self.folder)))



XPI_GECKO_ID = 'xpi-install@oganesson.test'


def xpi_add_on(gecko_id):
    """An .xpi, as AMO serves it: with its signature in META-INF/."""
    manifest = {
        'manifest_version': 2,
        'name': f'Firefox .xpi install test add-on {gecko_id or "without a Gecko ID"}',
        'version': '1',
        'background': {'scripts': ['background.js']},
        'permissions': ['storage'],
    }
    if gecko_id:
        manifest['browser_specific_settings'] = {'gecko': {'id': gecko_id}}
    files = {
        'manifest.json': json.dumps(manifest),
        'background.js': 'self.started = true;',
        'META-INF/cose.sig': 'not checked',
        'META-INF/mozilla.rsa': 'not checked',
    }
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return data.getvalue()


class FirefoxXpiInstallTest(BrowserTest):
    """A .xpi downloaded after a user gesture opens the install prompt.
    Accepted, an add-on with a Gecko ID installs packed, without developer
    mode, with the ID from its Gecko ID; a second download reinstalls it and
    keeps its storage. One without a Gecko ID doesn't install, even in
    developer mode, and without a gesture a .xpi stays a file."""

    prefs = DEVELOPER_MODE

    @classmethod
    def setUpClass(cls):
        xpi = (200, {'Content-Type': 'application/x-xpinstall'}, xpi_add_on(XPI_GECKO_ID))
        no_id = (200, {'Content-Type': 'application/x-xpinstall'}, xpi_add_on(None))
        cls.server = Server({'/': (200, {'Content-Type': 'text/html'}, b'<p>add-ons</p>'),
                             '/add-on.xpi': xpi, '/no-id.xpi': no_id, '/no-gesture.xpi': xpi})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def download(self, path, gesture=True):
        """Downloads `path` from a page of the server, as a click on a link
        to it does, or as the page does by itself without `gesture`."""
        page = self.browser.new_tab(self.server.url('/'))
        wait_for(lambda: page.eval('document.readyState') == 'complete', what='the page')
        page.eval(f"location.href = '{path}'", gesture=gesture)

    def accept_prompt(self):
        button = self.browser.wait_view(
            'MdTextButton', match=lambda v: v['Enabled'] == 'true' and v['Text'] == 'Add extension')
        self.browser.click_view(button)

    def installed(self, add_on):
        page = self.browser.new_tab('chrome://extensions')
        try:
            return page.eval(f"""new Promise(done => chrome.developerPrivate.getExtensionsInfo(
                {{includeDisabled: true}}, all => done(all.filter(e => e.id === '{add_on}')
                    .map(e => ({{location: e.location, state: e.state}})))))""")
        finally:
            self.browser.close_target(page)

    def started(self, add_on, check='true'):
        """The add-on's background once it has started and `check` holds."""
        def ready():
            try:
                background = self.browser.extension_background(add_on, timeout=1)
            except AssertionError:
                return None
            try:
                if background.eval(f'self.started === true && {check}'):
                    return background
            except (OSError, RuntimeError, ConnectionError):
                pass
            background.close()
            return None
        return wait_for(ready, timeout=30, what='the background script')

    def test_download_installs(self):
        # Chromium's ID of the Gecko ID: its SHA-256, in letters a to p.
        add_on = hashlib.sha256(XPI_GECKO_ID.encode()).hexdigest()[:32].translate(
            str.maketrans('0123456789abcdef', 'abcdefghijklmnop'))
        self.download('/add-on.xpi')
        self.accept_prompt()
        background = self.started(add_on)
        try:
            background.eval("browser.storage.local.set({kept: 'from the first install'})")
            background.eval('self.first = true')
        finally:
            background.close()
        info = self.installed(add_on)
        self.assertEqual(len(info), 1)
        self.assertNotEqual(info[0]['location'], 'UNPACKED')
        self.assertEqual(info[0]['state'], 'ENABLED')

        self.download('/add-on.xpi')
        self.accept_prompt()
        # The reinstalled add-on's new background page.
        background = self.started(add_on, '!self.first')
        try:
            stored = background.eval("browser.storage.local.get('kept')")
        finally:
            background.close()
        self.assertEqual(stored, {'kept': 'from the first install'})
        self.assertEqual(len(self.installed(add_on)), 1)

    def test_no_gecko_id(self):
        self.download('/no-id.xpi')
        wait_for(lambda: 'This add-on has no Gecko ID' in self.browser.log_path.read_text(
            errors='replace'), timeout=30, what='the load error')
        page = self.browser.new_tab('chrome://extensions')
        try:
            names = page.eval("""new Promise(done => chrome.developerPrivate.getExtensionsInfo(
                {includeDisabled: true}, all => done(all.map(e => e.name))))""")
        finally:
            self.browser.close_target(page)
        self.assertNotIn('Firefox .xpi install test add-on without a Gecko ID', names)

    def test_no_gesture(self):
        self.download('/no-gesture.xpi', gesture=False)
        wait_for(lambda: (self.browser.home / 'Downloads' / 'no-gesture.xpi').exists(),
                 what='the download')
        # The prompt would open as the download completes, in under a second.
        time.sleep(2)
        self.assertFalse([v for v in self.browser.views('MdTextButton', Text='Add extension')
                          if v.visible])


FIRST_PARTY_DOMAIN_ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox firstPartyDomain test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-first-party-domain@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['cookies', 'http://127.0.0.1/*'],
    }),
    'background.js': 'self.started = true;',
}

FIRST_PARTY_DOMAIN_CALLS = """(async () => {
    const error = async call => {
        try {
            return await call();
        } catch (e) {
            return e.message;
        }
    };
    const url = '%(url)s';
    const set = await browser.cookies.set({url, name: 'fpd', value: '1', firstPartyDomain: ''});
    const names = cookies => cookies.map(c => [c.name, c.firstPartyDomain]);
    return {
        set: [set.name, set.firstPartyDomain],
        setOther: await error(() => browser.cookies.set(
            {url, name: 'other', value: '1', firstPartyDomain: 'example.com'})),
        get: (await browser.cookies.get({url, name: 'fpd', firstPartyDomain: ''})).firstPartyDomain,
        getOther: await browser.cookies.get({url, name: 'fpd', firstPartyDomain: 'example.com'}),
        getAllNull: names(await browser.cookies.getAll({url, firstPartyDomain: null})),
        getAllEmpty: names(await browser.cookies.getAll({url, firstPartyDomain: ''})),
        getAllOther: names(await browser.cookies.getAll({url, firstPartyDomain: 'example.com'})),
        getAllPlain: names(await browser.cookies.getAll({url})),
        removeOther: await browser.cookies.remove({url, name: 'fpd', firstPartyDomain: 'example.com'}),
        remove: (await browser.cookies.remove({url, name: 'fpd', firstPartyDomain: ''})).name,
        left: names(await browser.cookies.getAll({url})),
    };
})()"""


class FirefoxFirstPartyDomainTest(BrowserTest):
    """Firefox's firstPartyDomain in the cookies API, as in Firefox with
    first-party isolation off: every cookie has "", "" or null matches every
    cookie, another value matches none, and set() refuses another value."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-first-party-domain-'))
        for file, text in FIRST_PARTY_DOMAIN_ADD_ON.items():
            (cls.folder / file).write_text(text)
        cls.browser_args = (f'--load-extension={cls.folder}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_first_party_domain(self):
        add_on = extension_id(self.folder)
        background = self.browser.extension_background(add_on)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
            result = background.eval(FIRST_PARTY_DOMAIN_CALLS % {'url': 'http://127.0.0.1/'})
        finally:
            background.close()
        self.assertEqual(result, {
            'set': ['fpd', ''],
            'setOther': 'firstPartyDomain must be "": first-party isolation is off',
            'get': '',
            'getOther': None,
            'getAllNull': [['fpd', '']],
            'getAllEmpty': [['fpd', '']],
            'getAllOther': [],
            'getAllPlain': [['fpd', '']],
            'removeOther': None,
            'remove': 'fpd',
            'left': [],
        })
        self.assertFalse(self.browser.extension_errors(add_on))


if __name__ == '__main__':
    unittest.main()
