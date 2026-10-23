"""The link hover bubble (oganesson/ui/status-bubble-full-url.patch).

Hovering a link shows its whole URL at once, in a bubble as wide as the URL,
which doesn't grow later. A URL wider than the window scrolls in the bubble.
The link menu has no "Open in reading mode" (oganesson/ui/no-reading-mode-menu-item.patch).
"""

import time
import unittest
import urllib.parse

from harness import BrowserTest, wait_for

MEDIUM = 'https://example.com/' + 'medium-path/' * 6
LONG = 'https://example.com/' + 'a-very-long-path-segment/' * 20
PAGE = 'data:text/html,' + urllib.parse.quote(
    f'<a id=medium href="{MEDIUM}" style="font-size:40px">medium</a><br>'
    f'<a id=long href="{LONG}" style="font-size:40px">long</a>')


class StatusBubbleTest(BrowserTest):

    def hover(self, page, selector):
        contents = self.browser.wait_view('ContentsWebView')
        x, y = page.eval(f'(() => {{ const r = document.querySelector("{selector}")'
                         '.getBoundingClientRect(); return [r.x + 5, r.y + r.height / 2]; })()')
        self.browser.xdotool('mousemove', str(contents.bounds['x'] + int(x)),
                             str(contents.bounds['y'] + int(y)))
        return wait_for(self.bubble, what='the status bubble')

    def bubble(self):
        return next((v for v in self.browser.views('StatusView') if v.visible), None)

    def text_x(self):
        bubble = self.bubble()
        return next(v.bounds['x'] for v in self.browser.views('Label')
                    if v.widget == bubble.widget)

    def test_1_full_width_at_once(self):
        page = self.browser.new_tab(PAGE)
        window = self.browser.wait_view('ContentsWebView').bounds['width']
        self.hover(page, '#medium')
        time.sleep(0.3)
        width = self.bubble().bounds['width']
        # Chromium's bubble starts at a third of the window and widens 1.6 s later.
        self.assertGreater(width, window / 3 + 20)
        time.sleep(2.5)
        self.assertEqual(self.bubble().bounds['width'], width)

    def test_2_longer_than_window_scrolls(self):
        page = self.browser.new_tab(PAGE)
        self.hover(page, '#long')
        time.sleep(0.5)
        start = self.text_x()
        time.sleep(2)
        self.assertLess(self.text_x(), start)

    def test_3_no_reading_mode(self):
        page = self.browser.new_tab(PAGE)
        self.browser.wait_view('ContentsWebView')
        self.browser.click_element(page, '#medium', button=3)
        menus = wait_for(self.browser.menus, what='the link menu')
        titles = [v['Title'] for group in menus[-1] for v in group]
        self.browser.key('Escape')
        self.assertIn('Copy link address', [t.replace('&', '') for t in titles])
        self.assertFalse([t for t in titles if 'reading mode' in t.replace('&', '').lower()])


if __name__ == '__main__':
    unittest.main()
