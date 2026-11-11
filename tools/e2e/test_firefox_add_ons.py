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

from harness import BrowserTest, Page, extension_id, unpack_xpi, wait_for

ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox APIs test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-apis@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'permissions': ['menus'],
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

    def test_menus(self):
        # Firefox's name for contextMenus, with its permission: the item shows
        # in the page's context menu, and a click reaches the add-on.
        self.background_eval('true')  # The background has created the item.
        page = self.browser.new_tab('data:text/html,<body%20style=height:90vh>')
        try:
            wait_for(lambda: page.eval("location.protocol == 'data:' && document.readyState == 'complete'"),
                     what='the page')
            self.browser.click_element(page, 'body', button=3)
            item = wait_for(lambda: next((i for menu in self.browser.menus() for group in menu
                                          for i in group if i['Title'] == 'Firefox menu item'), None),
                            what='the add-on\'s menu item')
            self.browser.click_view(item)
            wait_for(lambda: not self.browser.menus(), what='the menu to close')
            self.assertEqual(self.background_eval('self.clicked'), 'firefox-item')
        finally:
            self.browser.close_target(page)


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


if __name__ == '__main__':
    unittest.main()
