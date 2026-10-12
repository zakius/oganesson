"""The address bar suggestion switches on Manage search engines.

The profile has history (a typed site and a page whose title starts with
"Zebra"), an unvisited bookmark, a past search on a local default
engine, and an open tab. chrome://omnibox, connected to the window's
omnibox, reports the real address bar's matches with their types while
typing into it. Defaults: no past search, and below the first match, pages
come before searches. Each source's switch removes its matches; "ahead"
brings Chromium's order back. Enter on a URL still navigates and Enter on
a word still searches, also with history off.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from harness import BrowserTest, Server, wait_for
from test_firefox_sync import FIND

MANIFEST = {'manifest_version': 3, 'name': 'Omnibox suggestions test', 'version': '1',
            'permissions': ['bookmarks'],
            'background': {'service_worker': 'background.js'}}
PAGES = {'/': 'Zebra home', '/zebra-one.html': 'Zebra stripes one',
         '/zebra-tab.html': 'Zebra tab',
         '/zebra-bookmark.html': 'Zebra bookmark', '/search': 'Results'}
PREFS = ('oganesson.omnibox.suggest_history', 'oganesson.omnibox.suggest_bookmarks',
         'oganesson.omnibox.suggest_open_tabs', 'oganesson.omnibox.suggest_past_searches',
         'oganesson.omnibox.search_suggestions_first')
DEFAULTS = dict(zip(PREFS, (True, True, True, False, False)))
# The last done response of the window's omnibox for `text`, as seen by
# chrome://omnibox.
RESULTS = """((text) => {
  const all = document.querySelector('omnibox-output').responsesHistory.flat()
      .filter(r => r.inputText === text && r.done);
  const last = all[all.length - 1];
  return last && last.combinedResults.map(m => ({
      type: m.type, provider: m.providerName, url: m.destinationUrl,
      contents: m.contents, tab: m.hasTabMatch, search: m.isSearchType}));
})"""


def is_page(row):
    return row['type'].startswith('history-') or row['type'] == 'bookmark-title'


class OmniboxSuggestionsTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.server = Server({path: (200, {'Content-Type': 'text/html'},
                                    f'<title>{title}</title>'.encode())
                             for path, title in PAGES.items()})
        cls.extension = Path(tempfile.mkdtemp(prefix='oganesson-omnibox-'))
        (cls.extension / 'manifest.json').write_text(json.dumps(MANIFEST))
        (cls.extension / 'background.js').write_text('')
        # chrome://omnibox loads chrome://favicon icons its CSP blocks, which
        # a dev build's WebUI otherwise takes as fatal.
        cls.browser_args = (f'--load-extension={cls.extension}',
                            '--disable-crash-on-webui-js-error')
        cls.prefs = {'search': {'suggest_enabled': False},
                     'default_search_provider_data': {'template_url_data': {
                         'short_name': 'Local', 'keyword': 'local',
                         'synced_guid': 'b6b2d6c2-1b2a-4d55-9b3e-0e5f1c0a7a01',
                         'url': cls.server.url('/search?q={searchTerms}')}}}
        super().setUpClass()
        # chrome://omnibox is an internal debugging page, off by default.
        cls.browser.quit()
        local_state = cls.browser.profile / 'Local State'
        state = json.loads(local_state.read_text())
        local_state.write_text(json.dumps(state | {'internal_only_uis_enabled': True}))
        cls.browser.start()
        cls.zebra = f'zebra.localhost:{cls.server.port}'
        cls.seed()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.extension)

    @classmethod
    def seed(cls):
        cls.debug = cls.browser.new_tab('chrome://omnibox')
        wait_for(lambda: cls.debug.eval("!!document.querySelector('omnibox-input')?.shadowRoot"
                                        "?.querySelector('#connect-window-omnibox')"),
                 what='chrome://omnibox')
        cls.debug.eval("document.querySelector('omnibox-input').shadowRoot"
                       ".querySelector('#connect-window-omnibox').click()")
        # Typed into the address bar: a site, a page, and a past search.
        cls.enter(f'http://{cls.zebra}/')
        cls.enter(cls.server.url('/zebra-one.html'))
        cls.enter('zebrafish facts')
        extension = cls.browser.page('background.js')
        wait_for(lambda: extension.eval('typeof chrome.bookmarks') == 'object',
                 what='the extension APIs')
        extension.eval(f"chrome.bookmarks.create({{title: 'Zebra bookmark', url: "
                       f"{json.dumps(cls.server.url('/zebra-bookmark.html'))}}})")
        cls.browser.new_tab(cls.server.url('/zebra-tab.html'))
        cls.settings = cls.browser.new_tab('chrome://settings/searchEngines')
        wait_for(lambda: cls.settings.eval(f"!!({FIND})('settings-omnibox-suggestions')"),
                 what='the address bar switches')
        # Typing goes to chrome://omnibox's address bar, so the open tab is
        # another tab's.
        cls.browser._get(f'/json/activate/{cls.debug.id}')
        # The history index has the visits once they come up.
        seen = []

        def indexed():
            seen[:] = cls.suggest('zebr')
            return {'/zebra-one.html', '/zebra-tab.html'} <= cls.urls(seen)
        try:
            wait_for(indexed, timeout=30, what='the visited pages in suggestions')
        except AssertionError as error:
            raise AssertionError(f'{error}: {seen}') from None

    @classmethod
    def type_done(cls, text):
        """Types `text` into the address bar; returns its matches, in order,
        once all providers are done."""
        cls.debug.eval("document.querySelector('omnibox-output').responsesHistory = [[]]")
        cls.browser.key('ctrl+l')
        cls.browser.xdotool('type', '--delay', '40', text)
        return wait_for(lambda: cls.debug.eval(f'{RESULTS}({json.dumps(text)})'),
                        what=f'suggestions for {text!r}')

    @classmethod
    def suggest(cls, text):
        rows = cls.type_done(text)
        cls.browser.key('Escape', 'Escape')
        return rows

    @classmethod
    def enter(cls, text):
        """Where Enter on `text` in a new tab goes."""
        tab = cls.browser.new_tab('about:blank')
        cls.type_done(text)
        cls.browser.key('Return')
        url = wait_for(lambda: next((t['url'] for t in cls.browser.targets()
                                     if t['id'] == tab.id and t['url'] != 'about:blank'), None),
                       what=f'the tab to leave about:blank for {text!r}')
        wait_for(lambda: tab.eval('document.readyState') == 'complete', what=url)
        cls.browser.close_target(tab)
        return url

    def set_prefs(self, **changes):
        values = dict(DEFAULTS, **{f'oganesson.omnibox.{k}': v for k, v in changes.items()})
        for name, value in values.items():
            self.settings.eval(f'chrome.settingsPrivate.setPref({json.dumps(name)}, '
                               f'{json.dumps(value)})')
        wait_for(lambda: all(self.pref(n) == v for n, v in values.items()), what='the prefs')

    def pref(self, name):
        return self.settings.eval(f'chrome.settingsPrivate.getPref({json.dumps(name)})'
                                  '.then(p => p.value)')

    def zebr(self, **prefs):
        self.set_prefs(**prefs)
        return self.suggest('zebr')

    @classmethod
    def urls(cls, rows):
        return {r['url'].split(str(cls.server.port))[-1] for r in rows if not r['search']}

    def assert_pages_before_searches(self, rows):
        kinds = [is_page(r) for r in rows[1:] if is_page(r) or r['search']]
        self.assertEqual(kinds, sorted(kinds, reverse=True), rows)

    def test_1_defaults(self):
        rows = self.zebr()
        self.assertNotIn('search-history', [r['type'] for r in rows], rows)
        self.assertFalse([r for r in rows if 'zebrafish' in r['contents']], rows)
        # The typed site inline-autocompletes, as in Chromium.
        self.assertIn(self.zebra, rows[0]['url'], rows)
        self.assertLessEqual({'/zebra-one.html', '/zebra-bookmark.html', '/zebra-tab.html'},
                             self.urls(rows), rows)
        self.assertIn('bookmark-title', [r['type'] for r in rows], rows)
        self.assertTrue([r for r in rows if r['tab'] and r['url'].endswith('/zebra-tab.html')],
                        rows)
        # The search for what was typed is still there, under the pages.
        self.assertTrue([r for r in rows if r['type'] == 'search-what-you-typed'], rows)
        self.assert_pages_before_searches(rows)

    def test_2_history_off(self):
        rows = self.zebr(suggest_history=False)
        self.assertFalse([r for r in rows if r['type'].startswith('history-')], rows)
        self.assertEqual(self.urls(rows) & {'/', '/zebra-one.html', '/zebra-tab.html'}, set(),
                         rows)
        self.assertIn('/zebra-bookmark.html', self.urls(rows), rows)

    def test_3_bookmarks_off(self):
        rows = self.zebr(suggest_bookmarks=False)
        self.assertNotIn('bookmark-title', [r['type'] for r in rows], rows)
        self.assertNotIn('/zebra-bookmark.html', self.urls(rows), rows)
        self.assertIn('/zebra-one.html', self.urls(rows), rows)

    def test_4_open_tabs_off(self):
        rows = self.zebr(suggest_open_tabs=False)
        self.assertFalse([r for r in rows if r['tab']], rows)
        self.assertIn('/zebra-tab.html', self.urls(rows), rows)

    def test_5_past_searches_on(self):
        rows = self.zebr(suggest_past_searches=True)
        self.assertTrue([r for r in rows if r['type'] == 'search-history'
                         and r['contents'] == 'zebrafish facts'], rows)
        self.assert_pages_before_searches(rows)

    def test_5b_past_search_typed_exactly(self):
        # SearchProvider merges the search for what's typed into a past search
        # of the same words; with past searches off, it stays as that search.
        self.set_prefs()
        rows = self.suggest('zebrafish facts')
        self.assertNotIn('search-history', [r['type'] for r in rows], rows)
        self.assertTrue([r for r in rows if r['type'] == 'search-what-you-typed'
                         and r['contents'] == 'zebrafish facts'], rows)

    def test_6_searches_ahead(self):
        rows = self.zebr(search_suggestions_first=True)
        self.assertIn(self.zebra, rows[0]['url'], rows)
        self.assertTrue(rows[1]['search'], rows)
        rows = self.zebr(search_suggestions_first=True, suggest_past_searches=True)
        kinds = [r['search'] for r in rows[1:] if is_page(r) or r['search']]
        self.assertEqual(kinds, sorted(kinds, reverse=True), rows)

    def test_7_enter(self):
        for prefs in ({}, {'suggest_history': False}):
            self.set_prefs(**prefs)
            with self.subTest(**prefs):
                url = f'http://{self.zebra}/zebra-one.html'
                self.assertEqual(self.enter(f'{self.zebra}/zebra-one.html'), url)
                self.assertEqual(self.enter('quokka'), self.server.url('/search?q=quokka'))
                self.assertEqual(self.enter('zebrafish facts'),
                                 self.server.url('/search?q=zebrafish+facts'))
        self.set_prefs()

    def test_8_settings_switches(self):
        self.set_prefs()
        section = f"({FIND})('settings-omnibox-suggestions').shadowRoot"
        for switch, pref in zip(('history', 'bookmarks', 'openTabs', 'pastSearches',
                                 'searchSuggestionsFirst'), PREFS):
            with self.subTest(switch=switch):
                self.settings.eval(f"{section}.querySelector('#{switch}').click()")
                wait_for(lambda: self.pref(pref) != DEFAULTS[pref], what=pref)
                self.settings.eval(f"{section}.querySelector('#{switch}').click()")
                wait_for(lambda: self.pref(pref) == DEFAULTS[pref], what=pref)
        self.assertFalse(self.pref('search.suggest_enabled'))
        self.settings.eval(f"{section}.querySelector('#searchSuggestToggle').click()")
        wait_for(lambda: self.pref('search.suggest_enabled'), what='search.suggest_enabled')
        self.settings.eval(f"{section}.querySelector('#searchSuggestToggle').click()")
        wait_for(lambda: not self.pref('search.suggest_enabled'), what='search.suggest_enabled')
        # Moved from the Search engine page.
        search = self.browser.new_tab('chrome://settings/search')
        wait_for(lambda: search.eval(f"!!({FIND})('settings-search-page')?.shadowRoot"
                                     "?.querySelector('#openDialogButton')"),
                 what='the Search engine page')
        self.assertFalse(search.eval(f"!!({FIND})('settings-search-page').shadowRoot"
                                     ".querySelector('#searchSuggestToggle')"))
        self.browser.close_target(search)


if __name__ == '__main__':
    unittest.main()
