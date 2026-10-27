"""The link hover bubble (oganesson/ui/status-bubble-full-url.patch).

Hovering a link shows its whole URL at once, in a bubble as wide as the URL,
which doesn't grow later. A URL wider than the window scrolls in the bubble.
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
        x, y = wait_for(lambda: page.eval(
            f'(() => {{ const r = document.querySelector("{selector}")'
            '?.getBoundingClientRect(); return r && [r.x + 5, r.y + r.height / 2]; })()'),
            what=selector)
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
        width = self.browser.wait_view('StatusView').bounds['width']
        # Chromium's bubble starts at a third of the window and widens 1.6 s later.
        self.assertGreater(width, window / 3 + 20)
        # Past Chromium's widening, which must not come.
        time.sleep(2.5)
        self.assertEqual(self.bubble().bounds['width'], width)

    def test_2_longer_than_window_scrolls(self):
        page = self.browser.new_tab(PAGE)
        self.hover(page, '#long')
        self.browser.wait_view('StatusView')
        start = self.text_x()
        wait_for(lambda: self.text_x() < start, what='the text to scroll')


if __name__ == '__main__':
    unittest.main()
