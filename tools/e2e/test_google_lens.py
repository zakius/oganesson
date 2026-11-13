"""The opt-in "Search image with Google Lens" item (oganesson/core/google-lens.patch).

An image's context menu has no Lens item by default. The switch on
Settings > Search engine adds it, and choosing it uploads the image to Lens.
With Google as the engine, the engine's own item already goes to Lens, so the
menu has no second one.

--host-resolver-rules sends Lens's host to a local HTTPS server, which records
the upload.
"""

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from harness import BrowserTest, Page, Server, wait_for
from test_browser_traffic import certificate
from test_firefox_sync import FIND

PREF = 'oganesson.google.lens_enabled'
LENS_HOST = 'lens.google.com'
LENS_ITEM = 'Search image with Google Lens'
GOOGLE_ITEM = 'Search image with Google'


def png(size=64):
    """A red square."""
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))
    rows = b''.join(b'\0' + b'\xff\0\0' * size for _ in range(size))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


class LensTest(BrowserTest):
    """A page with an image, and a Lens stand-in."""

    prefs_extra = {}

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-lens-'))
        cls.lens = Server({'/upload': (200, {'Content-Type': 'text/html'},
                                       b'<title>lens</title>')},
                          tls=certificate(cls.folder, LENS_HOST))
        cls.site = Server({
            '/': (200, {'Content-Type': 'text/html'},
                  b'<title>image</title><img id="image" src="/red.png" width="200" height="200">'),
            '/red.png': (200, {'Content-Type': 'image/png'}, png())})
        cls.browser_args = (f'--host-resolver-rules=MAP {LENS_HOST} 127.0.0.1:{cls.lens.port}',
                            '--ignore-certificate-errors')
        cls.prefs = cls.prefs_extra or None
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.lens.stop()
        cls.site.stop()

    def open_image(self):
        page = self.browser.new_tab(self.site.url('/'))
        wait_for(lambda: page.eval("document.querySelector('#image')?.complete === true"
                                   " && document.querySelector('#image').naturalWidth > 0"),
                 what='the image')
        return page

    def image_menu(self, page):
        """The titles of the image's context menu, left open."""
        self.browser.click_element(page, '#image', button=3)
        wait_for(self.browser.menus, what='the context menu')
        return [i['Title'] for menu in self.browser.menus() for group in menu for i in group]

    def close_menu(self):
        self.browser.key('Escape')
        wait_for(lambda: not self.browser.menus(), what='the menu to close')

    def choose(self, title):
        item = next(i for menu in self.browser.menus() for group in menu for i in group
                    if i['Title'] == title)
        self.browser.click_view(item)
        wait_for(lambda: not self.browser.menus(), what='the menu to close')

    def assert_uploads(self, title):
        """Choosing `title` posts the image to Lens's upload page in a new tab."""
        before = {t['id'] for t in self.browser.targets()}
        self.lens.posts.clear()
        self.choose(title)
        wait_for(lambda: self.lens.posts, what='the upload at Lens')
        # Lens's upload form, with the image as a JPEG thumbnail.
        self.assertIn(b'name="encoded_image"', self.lens.posts[0])
        self.assertIn(b'Content-Type: image/jpeg\r\n\r\n\xff\xd8\xff', self.lens.posts[0])
        tab = wait_for(lambda: next((t for t in self.browser.targets() if t['type'] == 'page'
                                     and t['id'] not in before), None), what='the Lens tab')
        self.browser.close_target(Page(tab))


class DefaultEngineTest(LensTest):
    """DuckDuckGo, the default engine, has no image search."""

    def test_switch_adds_the_item(self):
        page = self.open_image()
        try:
            self.assertNotIn(LENS_ITEM, self.image_menu(page))
            self.close_menu()

            settings = self.browser.new_tab('chrome://settings/search')
            toggle = (f"({FIND})('settings-search-page')?.shadowRoot"
                      "?.querySelector('#googleLens')")
            wait_for(lambda: settings.eval(f'!!{toggle}'), what='the switch')
            self.assertEqual(settings.eval(f'{toggle}.label'), 'Search images with Google Lens')
            self.assertIs(settings.eval(f'{toggle}.checked'), False)
            settings.eval(f'{toggle}.click()')
            get = f'chrome.settingsPrivate.getPref({json.dumps(PREF)}).then(p => p.value)'
            wait_for(lambda: settings.eval(get) is True, what='the pref on')
            self.browser.close_target(settings)

            page.call('Page.bringToFront')
            self.assertEqual(self.image_menu(page).count(LENS_ITEM), 1)
            self.assert_uploads(LENS_ITEM)
        finally:
            self.browser.close_target(page)


class GoogleEngineTest(LensTest):
    """With Google as the engine and the switch on, the engine's own item
    goes to Lens, and there is no second one."""

    prefs_extra = {
        'oganesson': {'google': {'lens_enabled': True}},
        'default_search_provider_data': {'template_url_data': {
            'short_name': 'Google', 'keyword': 'google.com', 'prepopulate_id': 1,
            'synced_guid': '0f4a5a7e-3c1d-4b8e-9d0a-6b2f1e7c9a11',
            'url': 'https://www.google.com/search?q={searchTerms}',
            'image_url': f'https://{LENS_HOST}/upload',
            'image_url_post_params': 'encoded_image={google:imageThumbnail}'}}}

    def test_one_lens_item(self):
        page = self.open_image()
        try:
            titles = self.image_menu(page)
            self.assertNotIn(LENS_ITEM, titles)
            self.assertEqual(titles.count(GOOGLE_ITEM), 1)
            self.assert_uploads(GOOGLE_ITEM)
        finally:
            self.browser.close_target(page)


if __name__ == '__main__':
    unittest.main()
