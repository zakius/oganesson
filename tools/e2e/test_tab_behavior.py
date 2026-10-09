"""Firefox's tab rules, always on (docs/tab-behavior.md): where new tabs open
and which tab is selected after closing one. The scenarios are ported from
Firefox's browser_new_tab_insert_position.js. Tabs are named by their page:
`a` has the links `1` to `3`, `new` is a new tab page.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

from harness import BrowserTest, Server, wait_for

# An unpacked extension that inspects and arranges the tabs.
MANIFEST = {
    'manifest_version': 3,
    'name': 'Tab behavior test',
    'version': '1',
    'permissions': ['tabs', 'tabGroups'],
    'background': {'service_worker': 'background.js'},
}
NEXT_TO_ACTIVE = 'helium.browser.new_tab_next_to_active'
PAGE = (b'<!doctype html><title>page</title>'
        + b''.join(b'<p><a id="l%d" href="/%d">link %d</a>' % (i, i, i) for i in (1, 2, 3)))


class TabBehaviorTest(BrowserTest):
    """Shared steps."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-tab-behavior-'))
        (cls.folder / 'manifest.json').write_text(json.dumps(MANIFEST))
        (cls.folder / 'background.js').write_text('')
        cls.server = Server({f'/{name}': (200, {'Content-Type': 'text/html'}, PAGE)
                             for name in ('a', 'b', 'c', 'd', '1', '2', '3')})
        cls.browser_args = (f'--load-extension={cls.folder}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def run_js(self, body):
        page = self.browser.page('background.js')
        wait_for(lambda: page.eval('typeof chrome.tabs') == 'object', what='the extension APIs')
        return page.eval(f'(async () => {{ {body} }})()')

    def tabs(self):
        """The window's tabs by name, the active one in brackets."""
        return self.run_js("""
            const tabs = await chrome.tabs.query({windowType: 'normal'});
            return tabs.sort((x, y) => x.index - y.index).map(t => {
                const url = t.pendingUrl || t.url;
                const name = url.startsWith('http') ? new URL(url).pathname.slice(1) : 'new';
                return t.active ? `[${name}]` : name;
            }).join(' ');""")

    def assert_tabs(self, expected):
        try:
            wait_for(lambda: self.tabs() == expected, timeout=10, what=expected)
        except AssertionError:
            pass
        self.assertEqual(self.tabs(), expected)

    def start_with(self, *names):
        """Only tabs `names`, opened without an opener or owner, the first one
        active and loaded."""
        urls = [self.server.url(f'/{name}') for name in names]
        self.run_js(f"""
            const old = await chrome.tabs.query({{}});
            const urls = {json.dumps(urls)};
            await chrome.tabs.create({{url: urls[0], index: 0, active: true}});
            // First, as pinned tabs would move the others.
            await chrome.tabs.remove(old.map(t => t.id));
            for (const [i, url] of urls.slice(1).entries())
                await chrome.tabs.create({{url, index: i + 1, active: false}});""")
        page = wait_for(lambda: next((t for t in self.browser.targets()
                                      if t['url'] == urls[0]), None), what='the first tab')
        self.page = self.browser.page(page['url'])
        wait_for(lambda: self.page.eval("!!document.querySelector('#l3')"), what='its links')
        self.assert_tabs(' '.join([f'[{names[0]}]', *names[1:]]))

    def middle_click(self, link):
        """Opens link `link` of the active tab `a` in a background tab."""
        self.browser.click_element(self.page, f'#l{link}', button=2)

    def select(self, position):
        self.browser.key(f'ctrl+{position}')
        # Firefox's selectMRUOnClose test waits between switches as well.
        time.sleep(0.1)

    def settings(self):
        page = self.browser.new_tab('chrome://settings/appearance')
        wait_for(lambda: page.eval('!!window.chrome?.settingsPrivate'), what='settings')
        return page

    def set_prefs(self, prefs):
        """Sets `prefs` for the rest of the test."""
        page = self.settings()
        old = {name: page.eval(f'chrome.settingsPrivate.getPref({json.dumps(name)})')['value']
               for name in prefs}
        self.addCleanup(self.set_prefs_now, old)
        self.browser.close_target(page)
        self.set_prefs_now(prefs)

    def set_prefs_now(self, prefs):
        page = self.settings()
        for name, value in prefs.items():
            page.eval(f'chrome.settingsPrivate.setPref({json.dumps(name)}, {json.dumps(value)})')
        self.browser.close_target(page)

    def create_with_opener(self, name):
        """An add-on's background tab `name` with the active tab as its opener."""
        self.run_js(f"await chrome.tabs.create({{url: '{self.server.url('/' + name)}', "
                    "active: false, openerTabId: (await chrome.tabs.query({active: true}))[0].id});")


class FirefoxTabBehaviorTest(TabBehaviorTest):
    def test_links_chain_after_the_opener(self):
        self.start_with('a', 'b')
        for link in (1, 2, 3):
            self.middle_click(link)
            self.assert_tabs(' '.join(['[a]', *map(str, range(1, link + 1)), 'b']))

    def test_foreground_link_after_the_background_ones(self):
        self.start_with('a', 'b')
        self.middle_click(1)
        self.assert_tabs('[a] 1 b')
        self.page.eval("void window.open('/2')")
        self.assert_tabs('a 1 [2] b')

    def test_new_tab_opens_at_the_end_and_closes_to_the_previous_tab(self):
        self.start_with('a', 'b')
        self.browser.key('ctrl+t')
        self.assert_tabs('a b [new]')
        # A foreground tab is owned by the tab selected before it.
        self.browser.key('ctrl+w')
        self.assert_tabs('[a] b')

    def test_closing_a_link_tab_selects_its_opener(self):
        self.start_with('a', 'b')
        self.page.eval("void window.open('/1')")
        self.assert_tabs('a [1] b')
        self.browser.key('ctrl+w')
        self.assert_tabs('[a] b')
        # A background link tab is owned by its opener too, and selecting it
        # keeps that.
        self.middle_click(1)
        self.assert_tabs('[a] 1 b')
        self.select(2)
        self.browser.key('ctrl+w')
        self.assert_tabs('[a] b')

    def test_switching_away_ends_the_owner(self):
        self.start_with('a', 'b')
        self.page.eval("void window.open('/1')")
        self.assert_tabs('a [1] b')
        self.select(3)
        self.select(2)
        self.browser.key('ctrl+w')
        self.assert_tabs('a [b]')

    def test_second_link_tab_ends_the_first_ones_owner(self):
        self.start_with('a', 'b')
        self.middle_click(1)
        self.middle_click(2)
        self.assert_tabs('[a] 1 2 b')
        # Neither link tab is owned now: closing either selects its right
        # neighbour, where Chromium selects the other link tab.
        self.select(3)
        self.browser.key('ctrl+w')
        self.assert_tabs('a 1 [b]')
        self.select(2)
        self.browser.key('ctrl+w')
        self.assert_tabs('a [b]')

    def test_a_tab_switch_ends_the_run_of_links(self):
        self.start_with('a', 'b')
        self.middle_click(1)
        self.middle_click(2)
        self.select(4)
        self.select(1)
        self.middle_click(3)
        self.assert_tabs('[a] 3 1 2 b')

    def test_background_tab_without_opener_has_no_owner(self):
        self.start_with('a', 'b')
        # An add-on's tabs.create() has no opener.
        self.run_js(f"await chrome.tabs.create({{url: '{self.server.url('/c')}', "
                    "index: 1, active: false});")
        self.assert_tabs('[a] c b')
        self.select(2)
        self.browser.key('ctrl+w')
        self.assert_tabs('a [b]')

    def test_add_on_tab_with_opener_opens_after_it(self):
        # Firefox's ext-tabs.js makes openerTabId the tab's owner and opener,
        # in the background too.
        self.start_with('a', 'b')
        create = ("await chrome.tabs.create({url: '%s', active: false, "
                  "openerTabId: (await chrome.tabs.query({active: true}))[0].id});")
        self.run_js(create % self.server.url('/c'))
        self.assert_tabs('[a] c b')
        # After the opener's last related tab, which no longer has an owner.
        self.run_js(create % self.server.url('/d'))
        self.assert_tabs('[a] c d b')
        self.select(3)
        self.browser.key('ctrl+w')
        self.assert_tabs('[a] c b')
        self.select(2)
        self.browser.key('ctrl+w')
        self.assert_tabs('a [b]')

    def test_add_on_tab_with_opener_in_the_foreground_closes_to_it(self):
        self.start_with('a', 'b', 'c')
        self.run_js(f"await chrome.tabs.create({{url: '{self.server.url('/d')}', "
                    "openerTabId: (await chrome.tabs.query({url: '*://*/b'}))[0].id});")
        self.assert_tabs('a b [d] c')
        self.browser.key('ctrl+w')
        self.assert_tabs('a [b] c')

    def test_add_on_tab_at_an_index_joins_its_openers_group(self):
        # Firefox's addTab: tabGroup ?? openerTab.group, whatever the index.
        self.start_with('a', 'b', 'c')
        self.assertTrue(self.run_js(f"""
            const [a, b] = await chrome.tabs.query({{url: ['*://*/a', '*://*/b']}});
            const group = await chrome.tabs.group({{tabIds: [a.id, b.id]}});
            const tab = await chrome.tabs.create({{url: '{self.server.url('/d')}', active: false,
                                                    index: 3, openerTabId: a.id}});
            return (await chrome.tabs.get(tab.id)).groupId == group;"""))

    def test_moving_a_group_away_checks_only_the_active_tabs_owner(self):
        self.start_with('a', 'b', 'c', 'd')
        self.middle_click(1)
        # Closing d ends the run of links, so selecting b keeps 1's owner a.
        self.run_js("await chrome.tabs.remove((await chrome.tabs.query({url: '*://*/d'}))[0].id);")
        self.assert_tabs('[a] 1 b c')
        self.select(3)
        self.run_js("""
            const tabs = await chrome.tabs.query({url: ['*://*/1', '*://*/b']});
            const group = await chrome.tabs.group({tabIds: tabs.map(t => t.id)});
            const window = await chrome.windows.create({});
            await chrome.tabGroups.move(group, {windowId: window.id, index: -1});
            await chrome.windows.remove(window.id);""")
        self.assert_tabs('a [c]')

    def test_closing_the_last_tab_selects_the_one_on_its_left(self):
        self.start_with('a', 'b', 'c')
        self.select(3)
        self.browser.key('ctrl+w')
        self.assert_tabs('a [b]')

    def test_links_from_a_pinned_tab_open_after_the_pinned_tabs(self):
        self.start_with('a', 'c', 'b')
        tabs = "(await chrome.tabs.query({windowType: 'normal'})).sort((x, y) => x.index - y.index)"
        self.run_js(f"""const tabs = {tabs};
            for (const tab of tabs.slice(0, 2)) await chrome.tabs.update(tab.id, {{pinned: true}});""")
        self.assert_tabs('[a] c b')
        self.middle_click(1)
        self.middle_click(2)
        self.assert_tabs('[a] c 1 2 b')
        self.assertEqual(self.run_js(f'return {tabs}.map(t => t.pinned);'),
                         [True, True, False, False, False])

    def test_new_tab_next_to_the_active_tab(self):
        # Helium's switch is Firefox's browser.tabs.insertAfterCurrent.
        self.set_prefs({NEXT_TO_ACTIVE: True})
        self.start_with('a', 'b')
        self.browser.key('ctrl+t')
        self.assert_tabs('a [new] b')
