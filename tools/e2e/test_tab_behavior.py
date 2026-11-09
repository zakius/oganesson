"""Settings > Behavior > Tab behavior (docs/tab-behavior.md): where new tabs
open and which tab is selected after closing one, a Firefox (the default) or
Chromium preset of five knobs. The Firefox scenarios are ported from Firefox's
browser_new_tab_insert_position.js and browser_selectMRUOnClose.js. Tabs are
named by their page: `a` has the links `1` to `3`, `new` is a new tab page.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

from harness import BrowserTest, Server, extension_id, wait_for
from test_firefox_sync import FIND

# An unpacked extension that inspects and arranges the tabs.
MANIFEST = {
    'manifest_version': 3,
    'name': 'Tab behavior test',
    'version': '1',
    'permissions': ['tabs', 'tabGroups'],
    'background': {'service_worker': 'background.js'},
}
# The knobs' prefs, as the settings page names them.
LINK_POSITION = 'oganesson.tabs.link_position'
# Its values: Chromium's, Firefox's insertRelatedAfterCurrent, at the end.
LINKS_CHROMIUM, LINKS_AFTER_RELATED, LINKS_AT_END = 0, 1, 2
NEXT_TO_ACTIVE = 'helium.browser.new_tab_next_to_active'
SELECT_RELATED = 'oganesson.tabs.select_related_on_close'
SELECT_OWNER = 'oganesson.tabs.select_owner_on_close'
SELECT_MRU = 'oganesson.tabs.select_mru_on_close'
FIREFOX = {LINK_POSITION: LINKS_AFTER_RELATED, NEXT_TO_ACTIVE: False, SELECT_RELATED: False,
           SELECT_OWNER: True, SELECT_MRU: False}
CHROMIUM = {**FIREFOX, LINK_POSITION: LINKS_CHROMIUM, SELECT_RELATED: True}
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
        page = self.browser.extension_background(extension_id(self.folder))
        wait_for(lambda: page.eval('typeof self.chrome?.tabs') == 'object', what='the extension APIs')
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
        wait_for(lambda: self.tabs().split()[position - 1].startswith('['),
                 what=f'tab {position} selected')

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
    """The default: the Firefox preset, with no prefs set."""

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

    def test_links_at_the_end(self):
        # browser.tabs.insertRelatedAfterCurrent false, for an add-on's
        # openerTabId too.
        self.set_prefs({LINK_POSITION: LINKS_AT_END})
        self.start_with('a', 'b')
        self.middle_click(1)
        self.middle_click(2)
        self.assert_tabs('[a] b 1 2')
        self.create_with_opener('c')
        self.assert_tabs('[a] b 1 2 c')
        # A foreground link tab is still owned by the tab selected before it.
        self.page.eval("void window.open('/3')")
        self.assert_tabs('a b 1 2 c [3]')
        self.browser.key('ctrl+w')
        self.assert_tabs('[a] b 1 2 c')

    def test_links_next_to_the_active_tab_without_the_chain(self):
        # Firefox's insertAfterCurrent without insertRelatedAfterCurrent: each
        # link right after the active tab.
        self.set_prefs({LINK_POSITION: LINKS_AT_END, NEXT_TO_ACTIVE: True})
        self.start_with('a', 'b')
        self.middle_click(1)
        self.middle_click(2)
        self.assert_tabs('[a] 2 1 b')

    def test_closing_without_the_owner(self):
        # browser.tabs.selectOwnerOnClose false.
        self.set_prefs({SELECT_OWNER: False})
        self.start_with('a', 'b')
        self.page.eval("void window.open('/1')")
        self.assert_tabs('a [1] b')
        self.browser.key('ctrl+w')
        self.assert_tabs('a [b]')

    def test_z_most_recently_used_tab_on_close(self):
        self.set_prefs({SELECT_MRU: True})
        self.start_with('a', 'b', 'c', 'd')
        self.select(3)
        self.select(4)
        self.select(2)
        self.browser.key('ctrl+w')
        self.assert_tabs('a c [d]')
        # The owner still wins.
        self.select(1)
        self.page.eval("void window.open('/1')")
        self.assert_tabs('a [1] c d')
        self.browser.key('ctrl+w')
        self.assert_tabs('[a] c d')

    def test_settings_presets_and_knobs(self):
        settings = self.settings()
        section = f"({FIND})('settings-tab-behavior')?.shadowRoot"
        select = f"{section}.querySelector('#tabBehavior')"
        wait_for(lambda: settings.eval(f"!!{section}?.querySelector('#tabBehavior')"),
                 what='the Tab behavior menu')
        self.assertEqual(settings.eval(f"""[...{select}.options]
            .map(o => [o.value, o.textContent.trim(), o.disabled])"""),
            [['chromium', 'Chromium', False], ['firefox', 'Firefox', False],
             ['custom', 'Custom', True]])

        def knobs():
            return {name: settings.eval(f'chrome.settingsPrivate.getPref({json.dumps(name)})')['value']
                    for name in FIREFOX}

        def preset():
            return settings.eval(f'{select}.value')

        def choose(value):
            settings.eval(f"(s => {{ s.value = '{value}'; "
                          f"s.dispatchEvent(new Event('change')); }})({select})")

        links = f"{section}.querySelector('#linkPosition').shadowRoot.querySelector('select')"
        self.assertEqual(settings.eval(f"[...{links}.options].slice(0, 3)"
                                       ".map(o => [o.value, o.textContent.trim()])"),
                         [[str(LINKS_CHROMIUM), 'As in Chromium'],
                          [str(LINKS_AFTER_RELATED), 'As in Firefox'],
                          [str(LINKS_AT_END), 'At the end']])

        def choose_links(value):
            settings.eval(f"(s => {{ s.value = '{value}'; "
                          f"s.dispatchEvent(new Event('change')); }})({links})")

        def toggle(knob_id):
            settings.eval(f"{section}.querySelector('#{knob_id}').shadowRoot"
                          ".querySelector('cr-toggle').click()")

        # No prefs set: the Firefox preset.
        wait_for(lambda: preset() == 'firefox', what='Firefox shown')
        self.assertEqual(knobs(), FIREFOX)
        # A knob off the preset shows Custom, and back on it the preset.
        toggle('selectMruOnClose')
        wait_for(lambda: knobs() == {**FIREFOX, SELECT_MRU: True}, what='the knob saved')
        wait_for(lambda: preset() == 'custom', what='Custom shown')
        toggle('selectMruOnClose')
        wait_for(lambda: preset() == 'firefox', what='Firefox shown again')
        choose_links(LINKS_CHROMIUM)
        wait_for(lambda: preset() == 'custom', what='Custom shown for Chromium links')
        toggle('selectRelatedOnClose')
        wait_for(lambda: preset() == 'chromium', what='Chromium shown')
        self.assertEqual(knobs(), CHROMIUM)

        # Each preset resets every knob of any Custom combination.
        custom = {LINK_POSITION: LINKS_AT_END, NEXT_TO_ACTIVE: True, SELECT_RELATED: False,
                  SELECT_OWNER: False, SELECT_MRU: True}
        for chosen, expected in (('chromium', CHROMIUM), ('firefox', FIREFOX)):
            for name, value in custom.items():
                settings.eval(f'chrome.settingsPrivate.setPref({json.dumps(name)}, '
                              f'{json.dumps(value)})')
            wait_for(lambda: preset() == 'custom', what='Custom shown')
            choose(chosen)
            wait_for(lambda: knobs() == expected, what=f'the {chosen} knobs')
            wait_for(lambda: preset() == chosen, what=f'{chosen} shown')
        wait_for(lambda: settings.eval(f'{links}.value') == str(LINKS_AFTER_RELATED),
                 what='the Firefox link position shown')
        self.browser.close_target(settings)


class ChromiumTabBehaviorTest(TabBehaviorTest):
    """The Chromium preset: Chromium's own rules, unchanged."""
    prefs = {'oganesson': {'tabs': {'link_position': LINKS_CHROMIUM,
                                    'select_related_on_close': True}}}

    def check_chromium_link_order(self):
        self.start_with('a', 'b')
        self.middle_click(1)
        self.middle_click(2)
        self.assert_tabs('[a] 1 2 b')
        # A tab switch keeps the openers, so the next link goes after them.
        self.select(4)
        self.select(1)
        self.middle_click(3)
        self.assert_tabs('[a] 1 2 3 b')
        # A foreground link goes right after its tab.
        self.page.eval("void window.open('/c')")
        self.assert_tabs('a [c] 1 2 3 b')

    def test_link_order(self):
        self.check_chromium_link_order()

    def test_link_order_with_firefox_rules(self):
        # Another knob runs Firefox's rules, with Chromium's link positions.
        self.set_prefs({SELECT_MRU: True})
        self.check_chromium_link_order()

    def test_add_on_tab_with_opener_opens_at_the_end(self):
        # Chromium's tabs.create() with openerTabId.
        self.start_with('a', 'b')
        self.create_with_opener('c')
        self.create_with_opener('d')
        self.assert_tabs('[a] b c d')

    def test_add_on_tab_with_opener_with_firefox_rules(self):
        # Chromium's rule for a link from the opener.
        self.set_prefs({SELECT_MRU: True})
        self.start_with('a', 'b')
        self.create_with_opener('c')
        self.create_with_opener('d')
        self.assert_tabs('[a] c d b')

    def test_closing_a_link_tab_selects_a_sibling(self):
        self.start_with('a', 'b')
        self.middle_click(1)
        self.middle_click(2)
        self.assert_tabs('[a] 1 2 b')
        self.select(3)
        self.browser.key('ctrl+w')
        self.assert_tabs('a [1] b')

    def test_related_tabs_first_with_firefox_rules(self):
        # Another knob runs Firefox's rules, where Chromium's related tabs on
        # close still come first.
        self.set_prefs({SELECT_MRU: True})
        self.start_with('a', 'b')
        self.middle_click(1)
        self.middle_click(2)
        self.select(3)
        self.browser.key('ctrl+w')
        self.assert_tabs('a [1] b')

    def test_new_tab_next_to_the_active_tab(self):
        self.set_prefs({NEXT_TO_ACTIVE: True})
        self.start_with('a', 'b')
        self.browser.key('ctrl+t')
        self.assert_tabs('a [new] b')
