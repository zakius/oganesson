"""Vertical tabs: the window edge beside the tabs is clickable, and a middle
click on the strip's empty space opens a new tab, as in Firefox."""

import time

from harness import BrowserTest, wait_for


class VerticalTabsTest(BrowserTest):
    prefs = {'helium': {'browser': {'layout': 2}}}  # Helium's vertical layout

    def pages(self):
        return [t for t in self.browser.targets() if t['type'] == 'page']

    def region(self):
        return self.browser.wait_view('VerticalTabStripRegionView')

    def test_edge_click_selects_the_tab(self):
        last = self.browser.new_tab('data:text/html,<title>last</title>')
        wait_for(lambda: last.eval('document.visibilityState') == 'visible',
                 what='the new tab in front')
        tabs = self.browser.wait_settled(
            lambda: sorted((v for v in self.browser.views('TabView') if v.visible),
                           key=lambda v: v.bounds['y'])[:1], what='the tabs')
        x = self.region().bounds['x']
        # The first pixel column: the strip's padding, left of the top tab.
        self.assertLess(x + 1, tabs[0].bounds['x'])
        self.browser.xdotool('mousemove', str(x + 1), str(tabs[0].center[1]), 'click', '1')
        wait_for(lambda: last.eval('document.visibilityState') == 'hidden',
                 what='the top tab selected')

    def test_middle_click_on_empty_strip_opens_a_tab(self):
        before = len(self.pages())
        region = self.region()
        b = region.bounds
        # Below the tabs and the New Tab button.
        self.browser.xdotool('mousemove', str(b['x'] + b['width'] // 2),
                             str(b['y'] + b['height'] - 40), 'click', '2')
        wait_for(lambda: len(self.pages()) == before + 1, what='a new tab')
        # And no second one.
        time.sleep(0.5)
        self.assertEqual(len(self.pages()), before + 1)
