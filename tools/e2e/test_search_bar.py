"""The separate search bar (#57): searching with it, its own engine, and
moving it on the toolbar; Customize toolbar's reset hides it and restores the
order (#62); an engine that takes its terms by POST (#61).
"""

import json
import unittest

from harness import BrowserTest, Server, wait_for

CUSTOMIZE = 'chrome://customize-chrome-side-panel.top-chrome/?page=toolbar'
# Finds a match of `test` through shadow roots.
FIND = r"""(() => { const walk = (root) => { for (const el of root.querySelectorAll('*')) {
    if (TEST) return el;
    const found = el.shadowRoot && walk(el.shadowRoot); if (found) return found; } };
  return walk(document); })()"""
TOGGLE = FIND.replace('TEST', "el.localName === 'cr-toggle' && "
                              "el.getAttribute('aria-label') === 'Search bar'")
RESET = FIND.replace('TEST', "el.id === 'resetToDefaultButton'")


class SearchBarTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        results = (200, {'Content-Type': 'text/html'},
                   b'<!doctype html><title>Results</title>results')
        cls.server = Server({'/s': results, '/post': results})
        # A local default engine, so searches stay on this machine.
        cls.prefs = {
            'oganesson': {'search_bar': {'visible': True}},
            'default_search_provider_data': {'template_url_data': {
                'short_name': 'Local', 'keyword': 'local',
                'url': cls.server.url('/s?q={searchTerms}'),
                'synced_guid': '0b5a1e3c-7d1f-4d8e-9a55-6c1f3e2a9b10'}},
        }
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def pages(self):
        # DevTools lists pages by last activity, so the active tab first.
        return [t['url'] for t in self.browser.targets() if t['type'] == 'page']

    def field(self):
        return self.browser.wait_view('Textfield', match=lambda v: (
            v['PlaceholderText'] or '').startswith('Search with'))

    def search(self, text, *keys):
        self.browser.click_view(self.field())
        self.browser.key('ctrl+a')
        self.browser.xdotool('type', '--delay', '20', text)
        self.browser.key(*keys)

    def test_1_search_with_default_engine(self):
        self.assertEqual(self.field()['PlaceholderText'], 'Search with Local')
        self.search('hello world', 'Return')
        want = self.server.url('/s?q=hello+world')
        wait_for(lambda: self.pages()[0] == want, what=want)

    def test_2_alt_enter_opens_a_tab(self):
        before = len(self.pages())
        self.search('second', 'alt+Return')
        want = self.server.url('/s?q=second')
        wait_for(lambda: self.pages()[0] == want and len(self.pages()) == before + 1,
                 what=f'a new tab with {want}')

    def test_3_own_engine(self):
        # UI DevTools has no menu item titles: take the first engine that isn't
        # Local, which the placeholder then names.
        for index in range(2):
            self.browser.click_view(self.browser.wait_view(
                'ToolbarButton', TooltipText='Choose search engine'))
            engines = wait_for(lambda: self.browser.menus(), what='the engine menu')[0][0]
            self.assertGreater(len(engines), 1)
            self.browser.click_view(engines[index])
            placeholder = wait_for(lambda: self.field()['PlaceholderText'], what='placeholder')
            if placeholder != 'Search with Local':
                break
        self.assertNotEqual(placeholder, 'Search with Local')
        self.browser.quit()
        self.browser.start()
        self.assertEqual(self.field()['PlaceholderText'], placeholder)

    def test_4_move_on_toolbar(self):
        button = self.browser.wait_view('ToolbarButton', TooltipText='Choose search engine')
        back = self.browser.wait_view('BackForwardButton')
        x, y = button.center
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '1')
        for step in range(1, 11):
            self.browser.xdotool('mousemove', str(x + (back.bounds['x'] - x) * step // 10),
                                 str(y))
        self.browser.xdotool('mouseup', '1')
        wait_for(lambda: self.browser.wait_view('SearchBarView').bounds['x'] <
                 self.browser.wait_view('LocationBarView').bounds['x'],
                 what='the search bar left of the location bar')

    def test_5_hide_in_customize_toolbar(self):
        page = self.browser.new_tab(CUSTOMIZE)
        wait_for(lambda: page.eval(f'!!{TOGGLE}?.checked'), what='the Search bar toggle, on')
        page.eval(f'{TOGGLE}.click()')
        wait_for(lambda: not self.search_bar_visible(), what='the search bar to hide')
        self.browser.close_target(page)

    def search_bar_visible(self):
        return any(v.visible for v in self.browser.views('SearchBarView'))

    def test_5b_reset_to_default(self):
        page = self.browser.new_tab(CUSTOMIZE)
        # Only test_4's move customized the toolbar.
        wait_for(lambda: page.eval(f'{RESET} && !{RESET}.disabled'), what='reset enabled')
        page.eval(f'{TOGGLE}.click()')
        wait_for(self.search_bar_visible, what='the search bar to show')
        page.eval(f'{RESET}.click()')
        wait_for(lambda: not self.search_bar_visible(), what='reset to hide the search bar')
        wait_for(lambda: page.eval(f'{RESET}.disabled'), what='reset disabled')
        # Shown again, it is back in its default place, right of the location bar.
        page.eval(f'{TOGGLE}.click()')
        wait_for(lambda: self.browser.wait_view('SearchBarView').bounds['x'] >
                 self.browser.wait_view('LocationBarView').bounds['x'],
                 what='the search bar right of the location bar')
        self.browser.close_target(page)

    def test_6_post_engine(self):
        self.browser.quit()
        path = self.browser.profile / 'Default/Preferences'
        prefs = json.loads(path.read_text())
        prefs['oganesson']['search_bar'] = {'visible': True}
        prefs['default_search_provider_data']['template_url_data'].update(
            short_name='Local POST', url=self.server.url('/post'),
            search_url_post_params='q={searchTerms}')
        path.write_text(json.dumps(prefs))
        self.browser.start()
        wait_for(lambda: self.field()['PlaceholderText'] == 'Search with Local POST',
                 what='the POST engine')
        self.search('hello world', 'Return')
        wait_for(lambda: '/post' in self.server.bodies, what='a POST to /post')
        # Chromium sends an engine's POST parameters as multipart form data,
        # with the terms escaped as in a URL.
        content_type = self.server.headers['/post']['Content-Type']
        self.assertTrue(content_type.startswith('multipart/form-data; boundary='), content_type)
        body = self.server.bodies['/post'].decode()
        self.assertIn('name="q"\r\n\r\nhello%20world\r\n', body)


if __name__ == '__main__':
    unittest.main()
