"""The link hover bubble (oganesson/ui/status-bubble-full-url.patch).

Hovering a link shows its whole URL at once, in a bubble as wide as the URL,
which doesn't grow later. A URL wider than the window scrolls in the bubble.
"""

import unittest
import urllib.parse

from harness import BrowserTest, assert_never, wait_for

MEDIUM = 'https://example.com/' + 'medium-path/' * 6
LONG = 'https://example.com/' + 'a-very-long-path-segment/' * 20
PAGE = 'data:text/html,' + urllib.parse.quote(
    f'<a id=medium href="{MEDIUM}" style="font-size:40px">medium</a><br>'
    f'<a id=long href="{LONG}" style="font-size:40px">long</a>')


class StatusBubbleTest(BrowserTest):

    def hover(self, page, selector):
        contents = self.browser.wait_view('ContentsWebView')
        wait_for(lambda: page.eval(f'!!document.querySelector("{selector}")'), what=selector)
        x, y = page.eval(f'(() => {{ const r = document.querySelector("{selector}")'
                         '.getBoundingClientRect(); return [r.x + 5, r.y + r.height / 2]; })()')
        self.browser.xdotool('mousemove', str(contents.bounds['x'] + int(x)),
                             str(contents.bounds['y'] + int(y)))
        return self.browser.wait_settled(self.bubble, what='the status bubble')

    def bubble(self):
        return next((v for v in self.browser.views('StatusView') if v.visible), None)

    def text_x(self):
        bubble = self.bubble()
        return next(v.bounds['x'] for v in self.browser.views('Label')
                    if v.widget == bubble.widget)

    def test_1_full_width_at_once(self):
        page = self.browser.new_tab(PAGE)
        window = self.browser.wait_view('ContentsWebView').bounds['width']
        width = self.hover(page, '#medium').bounds['width']
        # Chromium's bubble starts at a third of the window and widens 1.6 s later.
        self.assertGreater(width, window / 3 + 20)
        assert_never(lambda: self.bubble().bounds['width'] != width, 2.5,
                     what='the bubble resized')

    def test_2_longer_than_window_scrolls(self):
        page = self.browser.new_tab(PAGE)
        self.hover(page, '#long')
        start = self.text_x()
        # It waits a second at its start, then scrolls.
        wait_for(lambda: self.text_x() < start, what='the URL to scroll')


if __name__ == '__main__':
    unittest.main()
