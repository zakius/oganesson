"""Split view drop target: a link dragged to the side of the page and dropped
on the panel that appears there opens in a new split, wherever on the panel it
drops. Runs on Wayland, where the compositor only drops on a target that took
the drag at the last pointer motion."""

import time

from harness import BrowserTest, Server, wait_for

# The page records where it gets dragover, and when the drag ends.
PAGE = (b'<title>source</title><body style="margin:0">'
        b'<a id="link" href="/target" style="position:absolute; left:50%; top:20%;'
        b' font-size:40px">drag me</a><script>self.overs = []; self.ended = false;'
        b' addEventListener("dragover", e => overs.push(`${e.clientX},${e.clientY}`));'
        b' addEventListener("dragend", () => ended = true);</script>')


class SplitViewDropTest(BrowserTest):
    wayland = True

    @classmethod
    def setUpClass(cls):
        cls.server = Server({
            '/': (200, {'Content-Type': 'text/html'}, PAGE),
            '/target': (200, {'Content-Type': 'text/html'}, b'<title>target</title>'),
        })
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def contents(self):
        # Containers: after a split, the second ContentsWebView stays visible
        # in a hidden container while a tab outside the split is shown.
        return [v for v in self.browser.views('ContentsContainerView') if v.visible]

    def drop_target(self):
        return next((v for v in self.browser.views('MultiContentsDropTargetView')
                     if v.visible), None)

    def start_drag(self):
        """Opens the page in a new tab (not in a split) and presses on its
        link. Returns the pointer position, the page's bounds and the page."""
        page = self.browser.new_tab(self.server.url('/'))
        wait_for(lambda: page.eval('!!document.getElementById("link")'
                                   ' && document.visibilityState == "visible"'), what='the page')
        wait_for(lambda: len(self.contents()) == 1, what='one page shown')
        bounds = self.contents()[0].bounds
        x, y = page.eval('(() => { const r = document.getElementById("link")'
                         '.getBoundingClientRect(); return [r.x + 20, r.y + r.height / 2]; })()')
        x, y = bounds['x'] + int(x), bounds['y'] + int(y)
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '1')
        # Past the drag threshold.
        for step in range(1, 6):
            self.browser.xdotool('mousemove', str(x + 3 * step), str(y + 3 * step))
            time.sleep(0.05)
        return (x + 15, y + 15), bounds, page

    def move(self, start, end):
        for step in range(1, 11):
            self.browser.xdotool('mousemove', str(start[0] + (end[0] - start[0]) * step // 10),
                                 str(start[1] + (end[1] - start[1]) * step // 10))
            time.sleep(0.05)

    def drag_to_left_edge(self):
        """Drags the link next to the page's left edge and holds the pointer
        still until the drop target is there at its full width. Returns the
        pointer position and the drop target."""
        start, bounds, page = self.start_drag()
        page.close()
        # Inside both the nudge and the full panel.
        edge = (bounds['x'] + 40, start[1])
        self.move(start, edge)
        # A link drag first shows a nudge (5% of the page, here 80 px), which
        # widens to the full panel (at least 120 px) once it takes the drag;
        # each step slides in over 300 ms.
        return edge, self.browser.wait_view('MultiContentsDropTargetView', timeout=10,
                                            match=lambda v: v.bounds['width'] >= 120)

    def assert_split(self):
        wait_for(lambda: len(self.contents()) == 2, what='a split with two pages')
        self.assertTrue(any(t['url'] == self.server.url('/target')
                            for t in self.browser.targets() if t['type'] == 'page'))

    def test_drop_on_the_plus_icon(self):
        pointer, target = self.drag_to_left_edge()
        self.move(pointer, target.center)
        # The drop target shows no hover, so give the drag's last moves time to reach it.
        time.sleep(0.5)
        self.browser.xdotool('mouseup', '1')
        self.assert_split()

    def test_drop_on_the_panel_with_a_resting_pointer(self):
        # The panel slides in under the pointer, away from the "+", and the
        # pointer doesn't move again before the drop.
        pointer, target = self.drag_to_left_edge()
        b = target.bounds
        self.assertTrue(b['x'] <= pointer[0] < b['x'] + b['width'], (pointer, b))
        self.assertGreater(abs(pointer[1] - target.center[1]), 60, 'away from the "+"')
        self.browser.xdotool('mouseup', '1')
        self.assert_split()

    def test_drop_in_the_middle_of_the_page(self):
        start, bounds, page = self.start_drag()
        middle = (bounds['x'] + bounds['width'] // 2, bounds['y'] + bounds['height'] * 2 // 3)
        self.move(start, middle)
        # The resting pointer's motion repeats every 350 ms: four dragovers at
        # one point are over a second of rest, past the drop target's delays
        # (500 ms, 1 s for the nudge).
        wait_for(lambda: page.eval('overs.length >= 4 && new Set(overs.slice(-4)).size == 1'),
                 what='the pointer to rest in the page')
        self.assertIsNone(self.drop_target())
        self.browser.xdotool('mouseup', '1')
        # A split would open as the drop is handled, before the drag ends.
        wait_for(lambda: page.eval('ended'), what='the drag to end')
        self.assertEqual(len(self.contents()), 1)
        page.close()
