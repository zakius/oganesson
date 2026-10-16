"""Settings → Import bookmarks and settings: besides the browsers it knows by
name, the dialog lists the profiles it finds by their files under the test's
HOME, named by kind and folder, and leaves out Thunderbird's. Importing from
such a profile brings its bookmarks and their favicons.

The "Choose a profile folder…" entry opens the native folder picker, which
these tests can't drive; they check only that it is listed.
"""

import json
import sqlite3
import struct
import zlib

from harness import BrowserTest, wait_for
from test_firefox_sync import FIND

DIALOG = f"({FIND})('settings-import-data-dialog')"
PAGE_URL = 'https://example.org/imported'


def png(rgb):
    """A 16x16 PNG of one colour."""
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))
    rows = b''.join(b'\0' + bytes(rgb) * 16 for _ in range(16))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 16, 16, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def chromium_profile(user_data, name, bookmarks=()):
    profile = user_data / 'Default'
    profile.mkdir(parents=True)
    (user_data / 'Local State').write_text(json.dumps(
        {'profile': {'info_cache': {'Default': {'name': name}}}}))
    # Brave's importer requires date_added, which every real Bookmarks file has.
    children = [{'type': 'url', 'name': title, 'url': url, 'date_added': '13300000000000000'}
                for title, url in bookmarks]
    (profile / 'Bookmarks').write_text(json.dumps({'roots': {
        'bookmark_bar': {'type': 'folder', 'name': 'Bookmarks bar', 'children': children},
        'other': {'type': 'folder', 'name': 'Other bookmarks', 'children': []}}}))
    return profile


def firefox_root(root, profile_dir):
    (root / profile_dir).mkdir(parents=True)
    (root / profile_dir / 'places.sqlite').write_bytes(b'')
    (root / 'profiles.ini').write_text(
        f'[Profile0]\nName=default\nIsRelative=1\nPath={profile_dir}\n')
    return root / profile_dir


class ImporterTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        home = cls.browser.home
        chromium_profile(home / '.config/vivaldi', 'Person 1', [('Known', 'https://example.org/')])
        profile = chromium_profile(home / '.config/SomeChromium', 'Work',
                                   [('Imported', PAGE_URL)])
        with sqlite3.connect(profile / 'Favicons') as db:
            db.executescript(
                'CREATE TABLE favicons (id INTEGER PRIMARY KEY, url TEXT, icon_type INTEGER);'
                'CREATE TABLE favicon_bitmaps (id INTEGER PRIMARY KEY, icon_id INTEGER,'
                ' image_data BLOB, width INTEGER, height INTEGER);'
                'CREATE TABLE icon_mapping (id INTEGER PRIMARY KEY, page_url TEXT,'
                ' icon_id INTEGER);')
            db.execute("INSERT INTO favicons VALUES (1, 'https://example.org/favicon.png', 1)")
            db.execute('INSERT INTO favicon_bitmaps VALUES (1, 1, ?, 16, 16)',
                       (png((200, 30, 30)),))
            db.execute('INSERT INTO icon_mapping VALUES (1, ?, 1)', (PAGE_URL,))
        firefox_root(home / '.somefox', 'abc.default')
        (firefox_root(home / '.thunderbird', 'mail.default') / 'Mail').mkdir()

    def open_dialog(self):
        page = self.browser.new_tab('chrome://settings/importData')
        wait_for(lambda: page.eval(f"{DIALOG}?.browserProfiles_?.length > 0"),
                 what='the import dialog')
        return page

    def test_lists_profiles_by_kind(self):
        page = self.open_dialog()
        names = page.eval(f"[...{DIALOG}.shadowRoot.querySelectorAll('#browserSelect option')]"
                          ".map(o => o.textContent.trim())")
        self.assertIn('Vivaldi - Person 1', names)
        self.assertIn('Chromium-based browser (SomeChromium) - Work', names)
        self.assertIn('Firefox-based browser (somefox)', names)
        self.assertIn('Choose a profile folder…', names)
        self.assertFalse([n for n in names if 'thunderbird' in n.lower()], names)
        self.assertEqual(1, sum('vivaldi' in n.lower() for n in names), names)

    def test_imports_bookmarks_and_favicons(self):
        page = self.open_dialog()
        index = page.eval(f"{DIALOG}.browserProfiles_.findIndex("
                          "p => p.name.includes('SomeChromium'))")
        self.assertGreaterEqual(index, 0)
        page.eval(f"""(() => {{ const dialog = {DIALOG};
            const select = dialog.shadowRoot.querySelector('#browserSelect');
            select.selectedIndex = {index};
            select.dispatchEvent(new Event('change')); }})()""")
        wait_for(lambda: page.eval(f"!{DIALOG}.shadowRoot.querySelector('#import').disabled"),
                 what='the import button')
        page.eval(f"{DIALOG}.shadowRoot.querySelector('#import').click()")
        wait_for(lambda: page.eval(f"{DIALOG}.importStatus_") in ('succeeded', 'failed'),
                 what='the import to end')
        self.assertEqual('succeeded', page.eval(f"{DIALOG}.importStatus_"))

        bookmarks = self.browser.new_tab('chrome://bookmarks')
        wait_for(lambda: bookmarks.eval(
            f"chrome.bookmarks.search({{url: {json.dumps(PAGE_URL)}}})"
            ".then(found => found.length)"), what='the imported bookmark')

        # The bookmarks page's own icon URL for the bookmark, drawn as it
        # would show it: the imported icon is red, the default globe grey.
        red = (f"new Promise(done => {{ const img = new Image();"
               f" img.onload = () => {{ try {{ const c = document.createElement('canvas');"
               f" c.width = c.height = 16; const g = c.getContext('2d');"
               f" g.drawImage(img, 0, 0); const [r, gr] = g.getImageData(8, 8, 1, 1).data;"
               f" done(r > 150 && gr < 80); }} catch (e) {{ done(String(e)); }} }};"
               f" img.onerror = () => done(false);"
               f" img.src = 'chrome://favicon2/?size=16&scaleFactor=1x&pageUrl=' +"
               f" encodeURIComponent({json.dumps(PAGE_URL)}) + '&allowGoogleServerFallback=0';"
               f" }})")
        wait_for(lambda: bookmarks.eval(red) is True, what='the imported favicon')
