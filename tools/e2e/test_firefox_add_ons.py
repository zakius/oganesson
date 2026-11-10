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

from harness import BrowserTest, extension_id, unpack_xpi, wait_for

ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Firefox APIs test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'firefox-apis@oganesson.test'}},
        'background': {'scripts': ['background.js']},
    }),
    'background.js': 'self.started = true;',
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


class FirefoxNamedTest(FirefoxAddOnsTest):
    """The same add-on, listed by its Gecko ID in the profile's list of add-ons
    that are told they run in Firefox."""
    prefs = {'firefox_add_ons': {'named_firefox': ['firefox-apis@oganesson.test']}}

    def test_runtime_get_browser_info(self):
        info = self.background_eval('browser.runtime.getBrowserInfo()')
        self.assertEqual((info['name'], info['vendor']), ('Firefox', 'Mozilla'))
        self.assertGreaterEqual(int(info['version'].split('.')[0]), 157)


if __name__ == '__main__':
    unittest.main()
