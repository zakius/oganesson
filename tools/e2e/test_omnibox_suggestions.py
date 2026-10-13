"""The address bar suggestion switches and order on Manage search engines.

The profile has history (a typed site and a page whose title starts with
"Zebra", and a typed site twit.localhost), unvisited bookmarks (one titled
"Twitter" on twittest.localhost), a past search on a local default engine,
and an open tab. chrome://omnibox, connected to the window's omnibox,
reports the real address bar's matches with their types while typing into
it. Defaults: no past search, and below the first match, bookmarks, history,
open tabs, then searches, and the what-you-typed URL last. Each source's
switch removes its matches; the order setting reorders the groups. Typing
the start of a site autofills it, from the first of bookmarks and history
in the order. Enter on a URL still navigates and Enter on a word still
searches, also with history off. While history isn't saved, history and
past searches are off and their switches greyed out, and come back as they
were when it is saved again. A profile with the old "Search suggestions
ahead" switch on gets searches first.
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
         '/zebra-bookmark.html': 'Zebra bookmark', '/search': 'Results', '/home': 'Twitter'}
PREFS = ('oganesson.omnibox.suggest_history', 'oganesson.omnibox.suggest_bookmarks',
         'oganesson.omnibox.suggest_open_tabs', 'oganesson.omnibox.suggest_past_searches')
ORDER = 'oganesson.omnibox.suggestion_order'
GROUPS = ['bookmarks', 'history', 'open_tabs', 'searches']
DEFAULTS = dict(zip(PREFS, (True, True, True, False))) | {ORDER: GROUPS}
# The last done response of the window's omnibox for `text`, as seen by
# chrome://omnibox.
RESULTS = """((text) => {
  const all = document.querySelector('omnibox-output').responsesHistory.flat()
      .filter(r => r.inputText === text && r.done);
  const last = all[all.length - 1];
  return last && last.combinedResults.map(m => ({
      type: m.type, provider: m.providerName, url: m.destinationUrl,
      contents: m.contents, tab: m.hasTabMatch, search: m.isSearchType,
      inline: m.inlineAutocompletion}));
})"""


def is_page(row):
    return row['type'].startswith('history-') or row['type'] == 'bookmark-title'


def group(row):
    """The order setting's group of a row, or 'guess' for the what-you-typed
    URL, which comes after them."""
    if row['type'] == 'url-what-you-typed':
        return 'guess'
    if row['search']:
        return 'searches'
    if row['tab']:
        return 'open_tabs'
    return 'bookmarks' if row['type'] == 'bookmark-title' else 'history'


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
        cls.twit = f'twittest.localhost:{cls.server.port}'
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
        cls.enter(f'http://twit.localhost:{cls.server.port}/')
        extension = cls.browser.page('background.js')
        wait_for(lambda: extension.eval('typeof chrome.bookmarks') == 'object',
                 what='the extension APIs')
        extension.eval(f"chrome.bookmarks.create({{title: 'Zebra bookmark', url: "
                       f"{json.dumps(cls.server.url('/zebra-bookmark.html'))}}})")
        extension.eval(f"chrome.bookmarks.create({{title: 'Twitter', url: "
                       f"'http://{cls.twit}/home'}})")
        # Found only by matching inside words, the way Firefox matches.
        extension.eval(f"chrome.bookmarks.create({{title: 'Reading list', url: "
                       f"'http://quillnews.localhost:{cls.server.port}/list'}})")
        for n in range(1, 7):
            extension.eval(f"chrome.bookmarks.create({{title: 'Okapi {n}', url: "
                           f"'http://okapi{n}.localhost:{cls.server.port}/page'}})")
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

    def assert_order(self, rows, order):
        """The rows below the first come in `order`'s groups, the
        what-you-typed URL last."""
        ranks = [(order + ['guess']).index(group(r)) for r in rows[1:]]
        self.assertEqual(ranks, sorted(ranks), rows)

    def test_1_defaults(self):
        rows = self.zebr()
        self.assertNotIn('search-history', [r['type'] for r in rows], rows)
        self.assertFalse([r for r in rows if 'zebrafish' in r['contents']], rows)
        # The site autofills, here from the bookmark on it.
        self.assertEqual(rows[0]['url'], f'http://{self.zebra}/', rows)
        self.assertEqual(rows[0]['inline'], f'a.localhost:{self.server.port}', rows)
        self.assertLessEqual({'/zebra-one.html', '/zebra-bookmark.html', '/zebra-tab.html'},
                             self.urls(rows), rows)
        self.assertIn('bookmark-title', [r['type'] for r in rows], rows)
        self.assertTrue([r for r in rows if r['tab'] and r['url'].endswith('/zebra-tab.html')],
                        rows)
        # The search for what was typed is still there, under the pages.
        self.assertTrue([r for r in rows if r['type'] == 'search-what-you-typed'], rows)
        self.assert_pages_before_searches(rows)
        self.assert_order(rows, GROUPS)
        self.assertLessEqual({'bookmarks', 'history', 'open_tabs', 'searches'},
                             {group(r) for r in rows[1:]}, rows)

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

    def test_6_order(self):
        for order in (['searches', 'history', 'bookmarks', 'open_tabs'],
                      ['open_tabs', 'searches', 'bookmarks', 'history']):
            with self.subTest(order=order):
                rows = self.zebr(suggestion_order=order, suggest_past_searches=True)
                self.assertIn(self.zebra, rows[0]['url'], rows)
                self.assertEqual(group(rows[1]), order[0], rows)
                self.assert_order(rows, order)
        # Autofill takes bookmarks and history in the order, then the
        # shortest site: twit.localhost is typed history, twittest.localhost
        # a bookmark.
        port = self.server.port
        for order, url in ((GROUPS, f'http://{self.twit}/'),
                           (['history', 'bookmarks', 'open_tabs', 'searches'],
                            f'http://twit.localhost:{port}/')):
            with self.subTest(order=order):
                self.set_prefs(suggestion_order=order)
                rows = self.suggest('twit')
                self.assertEqual(rows[0]['url'], url, rows)
                self.assertEqual(self.enter('twit'), url)
        self.set_prefs()

    def test_7_enter(self):
        for prefs in ({}, {'suggest_history': False}):
            self.set_prefs(**prefs)
            with self.subTest(**prefs):
                url = f'http://{self.zebra}/zebra-one.html'
                self.assertEqual(self.enter(f'{self.zebra}/zebra-one.html'), url)
                self.assertEqual(self.enter('quokka'), self.server.url('/search?q=quokka'))
                self.assertEqual(self.enter('zebrafish facts'),
                                 self.server.url('/search?q=zebrafish+facts'))
        # No autofill after a space.
        rows = self.suggest('twit ')
        self.assertTrue(rows[0]['search'], rows)
        self.set_prefs()

    def test_8_settings_switches(self):
        self.set_prefs()
        section = f"({FIND})('settings-omnibox-suggestions').shadowRoot"
        for switch, pref in zip(('history', 'bookmarks', 'openTabs', 'pastSearches'), PREFS):
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

    def test_8b_settings_order(self):
        self.set_prefs()
        self.addCleanup(self.set_prefs)
        section = f"({FIND})('settings-omnibox-suggestions').shadowRoot"

        def shown():
            return self.settings.eval(
                f"[...{section}.querySelectorAll('#order .list-item')].map(r => "
                "[r.dataset.group, r.classList.contains('off')])")

        def click(button):
            self.settings.eval(f"{section}.querySelector('#{button}').click()")

        wait_for(lambda: shown() == [[g, False] for g in GROUPS], what='the default order')
        self.assertTrue(self.settings.eval(f"{section}.querySelector('#bookmarks-up').disabled"))
        self.assertTrue(self.settings.eval(f"{section}.querySelector('#searches-down').disabled"))
        self.assertEqual(self.settings.eval(
            f"{section}.querySelector('#searches-up').getAttribute('aria-label')"),
            'Move Searches up')
        click('searches-up')
        order = ['bookmarks', 'history', 'searches', 'open_tabs']
        wait_for(lambda: self.pref(ORDER) == order, what='searches moved up')
        self.assertEqual([g for g, _ in shown()], order)
        # Keyboard focus follows the moved group.
        self.assertEqual(self.settings.eval(f'{section}.activeElement?.id'), 'searches-up')
        click('bookmarks-down')
        order = ['history', 'bookmarks', 'searches', 'open_tabs']
        wait_for(lambda: self.pref(ORDER) == order, what='bookmarks moved down')
        self.assertEqual([g for g, _ in shown()], order)
        # At the top, focus goes to the group's other button.
        click('bookmarks-up')
        wait_for(lambda: self.pref(ORDER)[0] == 'bookmarks', what='bookmarks moved up')
        self.assertEqual(self.settings.eval(f'{section}.activeElement?.id'), 'bookmarks-down')
        # A group whose switch is off stays in its place, greyed out.
        self.set_prefs(suggestion_order=order, suggest_bookmarks=False)
        wait_for(lambda: shown() == [['history', False], ['bookmarks', True],
                                     ['searches', False], ['open_tabs', False]],
                 what='bookmarks greyed out')

    def switch_state(self, switch):
        return self.settings.eval(
            f"(() => {{ const t = ({FIND})('settings-omnibox-suggestions').shadowRoot"
            f".querySelector('#{switch}'); return t && [t.checked, t.controlDisabled(),"
            " t.subLabel]; })()")

    def test_9_history_not_saved(self):
        # While history isn't saved, history and past searches are off and
        # greyed out; their prefs keep the user's choice for when it is again.
        self.set_prefs(suggest_past_searches=True)
        self.addCleanup(self.set_prefs)
        saving = 'history.saving_disabled'
        self.settings.eval(f'chrome.settingsPrivate.setPref({json.dumps(saving)}, true)')
        self.addCleanup(lambda: self.settings.eval(
            f'chrome.settingsPrivate.setPref({json.dumps(saving)}, false)'))
        wait_for(lambda: self.pref(saving), what=saving)
        note = 'Off while "Don\'t save browsing history" is on in Privacy and security'
        for switch in ('history', 'pastSearches'):
            wait_for(lambda: self.switch_state(switch) == [False, True, note],
                     what=f'{switch} off and greyed out')
        section = f"({FIND})('settings-omnibox-suggestions').shadowRoot"
        self.settings.eval(f"{section}.querySelector('#history').click()")
        self.assertEqual(self.switch_state('bookmarks')[:2], [True, False])
        self.assertTrue(self.pref('oganesson.omnibox.suggest_history'))
        self.assertTrue(self.pref('oganesson.omnibox.suggest_past_searches'))
        rows = self.suggest('zebr')
        self.assertFalse([r for r in rows if r['type'].startswith('history-')
                          or r['type'] == 'search-history'], rows)
        self.assertEqual(self.urls(rows) & {'/', '/zebra-one.html', '/zebra-tab.html'}, set(),
                         rows)
        self.assertFalse([r for r in rows if 'zebrafish' in r['contents']], rows)
        self.assertIn('/zebra-bookmark.html', self.urls(rows), rows)

        self.settings.eval(f'chrome.settingsPrivate.setPref({json.dumps(saving)}, false)')
        self.assertEqual(wait_for(lambda: self.switch_state('history')[1] is False
                                  and self.switch_state('history'), what='history back'),
                         [True, False, ''])
        wait_for(lambda: self.switch_state('pastSearches')[:2] == [True, False],
                 what='past searches back')
        rows = self.suggest('zebr')
        self.assertIn('/zebra-one.html', self.urls(rows), rows)
        self.assertTrue([r for r in rows if r['type'] == 'search-history'
                         and r['contents'] == 'zebrafish facts'], rows)

    def test_9b_user_setup(self):
        # History not saved, history and open tabs suggestions off: the
        # bookmark's site is the first row, completed inline, and Enter opens
        # it. The search for "twit" is there once, below the bookmark.
        self.set_prefs(suggest_history=False, suggest_open_tabs=False)
        self.addCleanup(self.set_prefs)
        saving = 'history.saving_disabled'
        self.settings.eval(f'chrome.settingsPrivate.setPref({json.dumps(saving)}, true)')
        self.addCleanup(lambda: self.settings.eval(
            f'chrome.settingsPrivate.setPref({json.dumps(saving)}, false)'))
        wait_for(lambda: self.pref(saving), what=saving)
        rows = self.suggest('twit')
        self.assertEqual(rows[0]['url'], f'http://{self.twit}/', rows)
        self.assertEqual(rows[0]['inline'], f'test.localhost:{self.server.port}', rows)
        self.assertEqual([r['type'] for r in rows[1:]],
                         ['bookmark-title', 'search-what-you-typed', 'url-what-you-typed'], rows)
        self.assertEqual(rows[1]['url'], f'http://{self.twit}/home', rows)
        self.assertEqual(self.enter('twit'), f'http://{self.twit}/')
        self.assertEqual(self.enter('quokka'), self.server.url('/search?q=quokka'))
        self.assertEqual(self.enter(f'{self.zebra}/zebra-one.html'),
                         f'http://{self.zebra}/zebra-one.html')
        # A typed scheme must be the site's; "www." doesn't count.
        rows = self.suggest('https://twit')
        self.assertNotEqual(rows[0]['url'], f'http://{self.twit}/', rows)
        rows = self.suggest('www.twit')
        self.assertEqual(rows[0]['url'], f'http://{self.twit}/', rows)
        # Typed into the path, the bookmarked page.
        rows = self.suggest(f'{self.twit}/h')
        self.assertEqual(rows[0]['url'], f'http://{self.twit}/home', rows)
        self.assertEqual(rows[0]['inline'], 'ome', rows)
        # Bookmarks off: no autofill, the search is first.
        self.set_prefs(suggest_history=False, suggest_open_tabs=False, suggest_bookmarks=False)
        rows = self.suggest('twit')
        self.assertEqual(rows[0]['type'], 'search-what-you-typed', rows)

    def test_9c_bookmark_matching(self):
        # Bookmarks match as in Firefox: anywhere in the title or address,
        # all of them up to the dropdown's size, not Chromium's 3.
        self.set_prefs()
        port = self.server.port
        rows = self.suggest('news')
        self.assertIn(f'http://quillnews.localhost:{port}/list', [r['url'] for r in rows], rows)
        rows = self.suggest('itter')
        self.assertIn(f'http://{self.twit}/home', [r['url'] for r in rows], rows)
        rows = self.suggest('okapi')
        self.assertLessEqual({f'http://okapi{n}.localhost:{port}/page' for n in range(1, 7)},
                             {r['url'] for r in rows}, rows)
        self.assertLessEqual(len(rows), 8, rows)
        # A site autofills; the 6 bookmarks follow.
        self.assertRegex(rows[0]['url'], rf'^http://okapi\d\.localhost:{port}/$')
        self.assertEqual([group(r) for r in rows[1:7]], ['bookmarks'] * 6, rows)
        # Only the first row autofills.
        self.assertEqual([r for r in rows[1:] if r['url'].endswith('/')], [], rows)


class OmniboxOrderMigrationTest(BrowserTest):
    """A profile with the old "Search suggestions ahead of history and
    bookmarks" switch on gets searches first in the order."""

    prefs = {'oganesson': {'omnibox': {'search_suggestions_first': True}}}

    def test_migration(self):
        settings = self.browser.new_tab('chrome://settings/searchEngines')
        wait_for(lambda: settings.eval(f"!!({FIND})('settings-omnibox-suggestions')"),
                 what='the address bar settings')
        # The address bar migrates the pref when it first suggests.
        self.browser.key('ctrl+l')
        self.browser.xdotool('type', 'a')
        def order():
            return settings.eval(
                f'chrome.settingsPrivate.getPref({json.dumps(ORDER)}).then(p => p.value)')
        wait_for(lambda: order() != GROUPS, what='the migrated order')
        self.assertEqual(order(), ['searches', 'bookmarks', 'history', 'open_tabs'])


if __name__ == '__main__':
    unittest.main()
