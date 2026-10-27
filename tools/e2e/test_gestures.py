"""Mouse gestures (docs/mouse-gestures.md), the X11 rows of the acceptance
matrix: strokes on ordinary, internal, event-cancelling, cross-origin, PDF,
and hung pages, across the browser's own UI and in incognito, a plain right
click, Shift and Ctrl, rocker and wheel gestures, no gesture under pointer
lock, and cancelled strokes. With OGANESSON_E2E_WAYLAND=1, the Wayland rows.

Real X11 input (xdotool), so events take the native path the recognizer
hooks, unlike DOM-generated events.
"""

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from harness import WAYLAND, BrowserTest, Page, Server, wait_for

IDC_BACK, IDC_FORWARD, IDC_SELECT_NEXT_TAB = 33000, 33001, 34016
# The PDF viewer extension.
PDF = 'mhjfbmdgcfjbbpaeojofohoefgiehjai'

def tiny_pdf():
    """A one-page PDF, with a correct xref table."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>']
    out, offsets = b'%PDF-1.4\n', []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b'%d 0 obj\n%s\nendobj\n' % (number, body)
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    out += b''.join(b'%010d 00000 n \n' % o for o in offsets)
    return out + b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (
        len(objects) + 1, xref)


# Every page counts the wheel events it gets, for handled().
PAGE = ('<!doctype html><title>{0}</title><body style="height:2000px">{0}{1}'
        '<script>self.wheels = 0; addEventListener("wheel", () => wheels++);</script></body>')
# Swallows every mouse, pointer and context menu event it sees.
CANCEL = ('<script>for (const t of ["mousedown", "mouseup", "mousemove", "pointerdown",'
          ' "pointerup", "contextmenu", "auxclick"]) addEventListener(t, e => {'
          ' e.preventDefault(); e.stopPropagation(); }, true);</script>')
# A page-sized #old control; logs the right button's DOM events, with their
# target, in `seen` and in localStorage under the page's path.
RECORD = ('<div id="old" style="position:fixed;inset:0"></div><script>self.seen = [];'
          ' for (const t of ["mousedown", "mouseup", "contextmenu", "auxclick"])'
          ' addEventListener(t, e => { if (e.button != 2) return;'
          ' seen.push(`${t} ${e.target.id}`);'
          ' localStorage[location.pathname] = JSON.stringify(seen); }, true);'
          ' oncontextmenu = e => e.preventDefault();</script>')


class GesturesTest(BrowserTest):
    prefs = {'oganesson': {'mouse_gestures': {
        'L': IDC_BACK, 'UL': IDC_BACK, 'R': IDC_FORWARD, 'rocker-rl': IDC_FORWARD,
        'wheel-down': IDC_SELECT_NEXT_TAB}}}

    @classmethod
    def setUpClass(cls):
        # Two local files cover file URL gestures without a browser add-on.
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-gestures-'))
        for name in ('A', 'B'):
            (cls.folder / f'{name}.html').write_text(PAGE.format(name, ''))
        page = lambda title, extra='': (200, {'Content-Type': 'text/html'},
                                        PAGE.format(title, extra).encode())
        cls.server = Server({'/a': page('A'), '/b': page('B'), '/cancel': page('Cancel', CANCEL),
                             '/inner': page('Inner', CANCEL),
                             '/doc.pdf': (200, {'Content-Type': 'application/pdf'}, tiny_pdf()),
                             '/hung': page('Hung', '<script>setTimeout(() => { for (;;); }, 300)'
                                                   '</script>'),
                             '/split': page('Split', '<p><a id="link" href="/b" '
                                                     'style="font-size: 40px">b</a>'),
                             '/lock': page('Lock', '<script>onclick = () =>'
                                                   ' document.body.requestPointerLock();'
                                                   ' onmouseup = e => self.released ||= e.button == 2;'
                                                   ' oncontextmenu = e => e.preventDefault()'
                                                   '</script>'),
                             '/record': page('Record', RECORD),
                             '/record2': page('Record2', RECORD)})
        cls.server.routes['/frame'] = page('Frame', (
            '<iframe style="position:fixed;inset:0;width:100%;height:100%;border:0" '
            f'src="{cls.server.url("/inner", "localhost")}"></iframe>'))
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def active(self):
        # DevTools lists pages by last activity, so the active tab first.
        return next(t for t in self.browser.targets() if t['type'] == 'page')

    def visit(self, first, second):
        """A tab that went from `first` to `second`, so it can go back."""
        page = self.browser.new_tab(first)
        wait_for(lambda: page.eval('location.href') == first and
                 page.eval('document.readyState') == 'complete', what=first)
        page.call('Page.navigate', url=second)
        wait_for(lambda: page.eval('location.href') == second and
                 page.eval('document.readyState') == 'complete', what=second)
        self.painted(page)
        return page

    @staticmethod
    def painted(page):
        # A new document takes input once it has painted.
        page.eval('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')

    def handled(self, page):
        """Waits until `page` gets a wheel up sent now. The browser handles
        input in order, so all input before it is handled, a stroke's release
        and any events it replays to the page included. With no button held,
        and the page at its top, the wheel does nothing else."""
        before = page.eval('wheels')
        self.browser.xdotool('click', '4')
        wait_for(lambda: page.eval('wheels') > before, what='the wheel up in the page')

    def center(self):
        return self.browser.wait_view('ContentsWebView').center

    def drag(self, x, y, dx, dy):
        """Moves the pointer from (x, y) by (dx, dy) in 8-pixel steps, and
        returns where it ends."""
        steps = max(abs(dx), abs(dy)) // 8
        for step in range(1, steps + 1):
            self.browser.xdotool('mousemove', str(x + dx * step // steps),
                                 str(y + dy * step // steps))
        return x + dx, y + dy

    def stroke_left(self, *hold, start=None):
        x, y = start or self.center()
        for key in hold:
            self.browser.xdotool('keydown', key)
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3')
        self.drag(x, y, -160, 0)
        self.browser.xdotool('mouseup', '3')
        for key in hold:
            self.browser.xdotool('keyup', key)

    def assert_goes_back(self, first, second):
        page = self.visit(first, second)
        self.stroke_left()
        wait_for(lambda: page.eval('location.href') == first, what=f'back to {first}')

    def test_ordinary_page(self):
        self.assert_goes_back(self.server.url('/a'), self.server.url('/b'))

    def test_page_cancelling_mouse_events(self):
        self.assert_goes_back(self.server.url('/a'), self.server.url('/cancel'))

    def test_cross_origin_iframe(self):
        self.assert_goes_back(self.server.url('/a'), self.server.url('/frame'))

    def test_internal_page(self):
        self.assert_goes_back('chrome://version/', 'chrome://credits/')

    def test_pdf(self):
        page = self.visit(self.server.url('/a'), self.server.url('/doc.pdf'))
        # The viewer, an extension's frame, loads after the document.
        viewer = Page(wait_for(lambda: next((t for t in self.browser.targets()
                                             if t['type'] == 'iframe'
                                             and t['url'].startswith(f'chrome-extension://{PDF}/')),
                                            None), what='the PDF viewer'))
        wait_for(lambda: viewer.eval('document.readyState') == 'complete', what='the viewer')
        self.painted(viewer)
        viewer.close()
        self.stroke_left()
        wait_for(lambda: page.eval('location.href') == self.server.url('/a'), what='back to /a')

    def test_hung_renderer(self):
        page = self.visit(self.server.url('/a'), self.server.url('/hung'))
        # Past the page's 300 ms timer: it spins then, and nothing can tell from outside.
        time.sleep(1)
        self.stroke_left()
        wait_for(lambda: any(t['url'] == self.server.url('/a') for t in self.browser.targets()),
                 what='back to /a')
        # Otherwise the "page unresponsive" dialog comes up during later tests.
        self.browser.close_target(page)

    def test_plain_right_click_opens_context_menu(self):
        page = self.visit(self.server.url('/a'), self.server.url('/b'))
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'click', '3')
        wait_for(lambda: self.browser.menus(), what='the context menu')
        self.browser.key('Escape')
        wait_for(lambda: not self.browser.menus(), what='the menu to close')
        self.assertEqual(page.eval('location.href'), self.server.url('/b'))

    def test_ctrl_bypasses(self):
        # The page gets the right button's events, and opens no menu.
        page = self.visit(self.server.url('/a'), self.server.url('/record'))
        self.stroke_left('ctrl')
        self.handled(page)
        self.assertIn('mouseup old', page.eval('seen'))
        self.assertEqual(page.eval('location.href'), self.server.url('/record'))

    def test_rocker(self):
        # Each left click with right held runs the command again.
        a, b, c = (self.server.url(p) for p in ('/a', '/b', '/split'))
        page = self.visit(a, b)
        page.call('Page.navigate', url=c)
        wait_for(lambda: page.eval('document.title') == 'Split', what=c)
        page.eval('history.go(-2)')
        wait_for(lambda: page.eval('location.href') == a, what='back to /a')
        self.painted(page)
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3', 'click', '1')
        wait_for(lambda: page.eval('location.href') == b, what='forward to /b')
        self.browser.xdotool('click', '1')
        wait_for(lambda: page.eval('location.href') == c, what='forward to /split')
        self.browser.xdotool('mouseup', '3')

    def test_declined_under_pointer_lock(self):
        # A locked pointer (games) has no usable screen position, so strokes
        # are left to the page.
        page = self.visit(self.server.url('/a'), self.server.url('/lock'))
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'click', '1')
        wait_for(lambda: page.eval('!!document.pointerLockElement'), what='the pointer lock')
        self.stroke_left()
        self.handled(page)
        self.assertTrue(page.eval('self.released'), 'the page got the release')
        self.assertEqual(page.eval('location.href'), self.server.url('/lock'))
        page.eval('document.exitPointerLock()')

    def test_second_window(self):
        # The stroke acts in the window it's drawn in, not the first one.
        first = self.visit(self.server.url('/a'), self.server.url('/b'))
        target = self.browser.browser_call('Target.createTarget', url=self.server.url('/a'),
                                           newWindow=True)['targetId']
        second = Page(wait_for(lambda: next((t for t in self.browser.targets()
                                             if t['id'] == target), None), what='window 2'))
        wait_for(lambda: second.eval('location.href') == self.server.url('/a') and
                 second.eval('document.readyState') == 'complete', what='window 2')
        second.call('Page.navigate', url=self.server.url('/cancel'))
        wait_for(lambda: second.eval('document.title') == 'Cancel' and
                 second.eval('document.readyState') == 'complete', what='/cancel')
        self.painted(second)
        self.stroke_left()
        wait_for(lambda: second.eval('location.href') == self.server.url('/a'),
                 what='back in window 2')
        self.assertEqual(first.eval('location.href'), self.server.url('/b'))
        self.browser.close_window(target)

    def test_split_view(self):
        # The stroke acts on the focused pane (a click focuses a pane).
        left = self.visit(self.server.url('/a'), self.server.url('/split'))
        before = {t['id'] for t in self.browser.targets()}
        self.browser.click_element(left, '#link', button=3)
        menu = wait_for(lambda: self.browser.menus(), what='the link menu')[0]
        # The first group: new tab, new window, split view, incognito.
        self.browser.click_view(menu[0][2])
        def split_panes():
            # The window with two visible contents views; others may be open.
            by_window = {}
            for view in self.browser.views('ContentsWebView'):
                if view.visible:
                    by_window.setdefault(view.widget, []).append(view)
            return next((v for v in by_window.values() if len(v) == 2), None)

        panes = self.browser.wait_settled(split_panes, what='two panes')
        right = wait_for(lambda: next((t for t in self.browser.targets()
                                       if t['id'] not in before and
                                       t['url'] == self.server.url('/b')), None),
                         what='the split pane')
        right = Page(right)
        wait_for(lambda: right.eval('location.href') == self.server.url('/b'), what='/b loaded')
        x, y = min(panes, key=lambda p: p.bounds['x']).center
        self.browser.xdotool('mousemove', str(x), str(y), 'click', '1')
        # Not the omnibox's widget: UI DevTools numbers nodes anew on each
        # query, so a menu closing in between renumbers the window.
        wait_for(lambda: left.eval('document.hasFocus()'), what='the left pane to take focus')
        self.browser.xdotool('mousedown', '3')
        for step in range(1, 21):
            self.browser.xdotool('mousemove', str(x - step * 8), str(y))
        self.browser.xdotool('mouseup', '3')
        wait_for(lambda: left.eval('location.href') == self.server.url('/a'), what='back on the left')
        self.assertEqual(right.eval('location.href'), self.server.url('/b'))

    def test_wheel(self):
        self.browser.new_tab(self.server.url('/a'))
        second = self.browser.new_tab(self.server.url('/b'))
        before = self.active()['id']
        self.assertEqual(before, second.id)
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3', 'click', '5',
                             'mouseup', '3')
        wait_for(lambda: self.active()['id'] != before, what='the next tab')

    def test_local_file(self):
        self.assert_goes_back((self.folder / 'A.html').as_uri(), (self.folder / 'B.html').as_uri())

    def test_stroke_from_a_tab(self):
        # The press opens no tab menu, and the release selects no other tab.
        page = self.visit(self.server.url('/a'), self.server.url('/b'))
        before = self.active()['id']
        tab = self.browser.wait_settled(
            lambda: max((v for v in self.browser.views('Tab') if v.visible),
                        key=lambda v: v.bounds['x'], default=None), what='the last tab')
        self.stroke_left(start=tab.center)
        wait_for(lambda: page.eval('location.href') == self.server.url('/a'), what='back to /a')
        self.assertEqual(self.active()['id'], before)
        self.assertEqual(self.browser.menus(), [])

    def test_empty_tab_strip_keeps_its_menu(self):
        # The empty part of the tab strip is the title bar: no gesture there,
        # and the right button opens its menu.
        page = self.visit(self.server.url('/a'), self.server.url('/b'))
        grab = self.browser.wait_view('FrameGrabHandle')
        self.stroke_left(start=(grab.bounds['x'] + grab.bounds['width'] // 2, grab.center[1]))
        wait_for(lambda: self.browser.menus(), what='the title bar menu')
        self.browser.key('Escape')
        wait_for(lambda: not self.browser.menus(), what='the menu to close')
        self.assertEqual(page.eval('location.href'), self.server.url('/b'))

    def test_stroke_from_the_toolbar(self):
        page = self.visit(self.server.url('/a'), self.server.url('/b'))
        self.stroke_left(start=self.browser.wait_view('LocationBarView').center)
        wait_for(lambda: page.eval('location.href') == self.server.url('/a'), what='back to /a')
        self.assertEqual(self.browser.menus(), [])

    def test_stroke_across_toolbar_and_tab_strip(self):
        # Up from the page over the toolbar, then left along the tab strip: UL.
        page = self.visit(self.server.url('/a'), self.server.url('/b'))
        before = self.active()['id']
        x, y = self.center()
        tabs_y = self.browser.wait_view('Tab').center[1]
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3')
        self.drag(*self.drag(x, y, 0, tabs_y - y), -160, 0)
        self.browser.xdotool('mouseup', '3')
        wait_for(lambda: page.eval('location.href') == self.server.url('/a'), what='back to /a')
        self.assertEqual(self.active()['id'], before)
        self.assertEqual(self.browser.menus(), [])

    def assert_cancelled(self, interrupt, then=lambda: None):
        """`interrupt()` halfway through a stroke left cancels it: the stroke
        runs nothing and the page gets none of the right button's events.
        After `then()`, the next stroke works, so nothing kept the pointer."""
        a, record = self.server.url('/a'), self.server.url('/record')
        page = self.visit(a, record)
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3')
        x, y = self.drag(x, y, -80, 0)
        interrupt()
        self.drag(x, y, -80, 0)
        self.browser.xdotool('mouseup', '3')
        then()
        self.handled(page)
        self.assertEqual(self.browser.menus(), [])
        self.assertEqual(page.eval('location.href'), record)
        self.assertEqual(page.eval('seen'), [])
        self.stroke_left()
        wait_for(lambda: page.eval('location.href') == a, what='back after the cancelled stroke')

    def test_escape_cancels(self):
        self.assert_cancelled(lambda: self.browser.xdotool('key', 'Escape'))

    def test_focus_loss_cancels(self):
        opened = []

        def open_window():
            page = Page(next(t for t in self.browser.targets() if t['type'] == 'page'))
            opened.append(self.browser.browser_call(
                'Target.createTarget', url='about:blank', newWindow=True)['targetId'])
            wait_for(lambda: not page.eval('document.hasFocus()'), what='the page to lose focus')
            page.close()

        def close_window():
            self.browser.close_window(opened[0])

        self.assert_cancelled(open_window, close_window)

    def test_capture_theft_cancels(self):
        # The app menu (Alt+F) takes the pointer.
        def open_menu():
            self.browser.xdotool('key', 'alt+f')
            wait_for(lambda: self.browser.menus(), what='the app menu')

        def close_menu():
            if self.browser.menus():
                self.browser.xdotool('key', 'Escape')
            wait_for(lambda: not self.browser.menus(), what='the menu to close')

        self.assert_cancelled(open_menu, close_menu)

    @unittest.skipIf(WAYLAND, 'the window is maximized, so no release lands outside it')
    def test_release_outside_the_window(self):
        # The stroke keeps the pointer past the window's edge.
        a, b = self.server.url('/a'), self.server.url('/b')
        page = self.visit(a, b)
        page.eval('history.back()')
        wait_for(lambda: page.eval('location.href') == a, what='back to /a')
        self.painted(page)
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3')
        self.drag(x, y, 1360 - x, 0)  # the window is 1300 wide, the screen 1400
        self.browser.xdotool('mouseup', '3')
        wait_for(lambda: page.eval('location.href') == b, what='forward to /b')
        self.stroke_left()
        wait_for(lambda: page.eval('location.href') == a, what='back to /a again')

    def test_incognito_window(self):
        def contexts():
            return {t['targetId']: t.get('browserContextId')
                    for t in self.browser.browser_call('Target.getTargets')['targetInfos']}

        before = contexts()
        self.browser.key('ctrl+shift+n')
        target = wait_for(lambda: next((t for t in self.browser.targets()
                                        if t['type'] == 'page' and t['id'] not in before), None),
                          what='the incognito window')
        self.assertNotIn(contexts()[target['id']], before.values())
        page = Page(target)
        try:
            for url in (self.server.url('/a'), self.server.url('/b')):
                page.call('Page.navigate', url=url)
                wait_for(lambda: page.eval('location.href') == url and
                         page.eval('document.readyState') == 'complete', what=url)
            self.painted(page)
            self.stroke_left()
            wait_for(lambda: page.eval('location.href') == self.server.url('/a'),
                     what='back to /a')
        finally:
            self.browser.close_window(target['id'])

    def test_shift_right_click_through_replay(self):
        # Helium's Shift+right-click shows the browser's menu on a page that
        # cancels contextmenu; the replayed press keeps Shift.
        page = self.visit(self.server.url('/a'), self.server.url('/cancel'))
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'click', '3')
        self.handled(page)
        self.assertEqual(self.browser.menus(), [])
        self.browser.xdotool('keydown', 'shift', 'click', '3', 'keyup', 'shift')
        wait_for(lambda: self.browser.menus(), what='the context menu')
        self.browser.key('Escape')
        wait_for(lambda: not self.browser.menus(), what='the menu to close')

    def test_control_replaced_while_pressed(self):
        # The replayed click hits the control there at release, not at press.
        page = self.visit(self.server.url('/a'), self.server.url('/record'))
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3')
        page.eval('old.outerHTML = \'<div id="new" style="position:fixed;inset:0"></div>\'')
        self.browser.xdotool('mouseup', '3')
        self.handled(page)
        self.assertEqual(page.eval('seen'), ['mousedown new', 'contextmenu new', 'mouseup new',
                                             'auxclick new'])

    def test_navigation_while_pressed(self):
        # The replayed click goes to the document there at release.
        page = self.visit(self.server.url('/a'), self.server.url('/record'))
        page.eval('localStorage.clear()')
        x, y = self.center()
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3')
        page.call('Page.navigate', url=self.server.url('/record2'))
        wait_for(lambda: page.eval('document.title') == 'Record2' and
                 page.eval('document.readyState') == 'complete', what='/record2')
        self.painted(page)
        self.browser.xdotool('mouseup', '3')
        self.handled(page)
        self.assertEqual(page.eval('seen'), ['mousedown old', 'contextmenu old', 'mouseup old',
                                             'auxclick old'])
        self.assertEqual(page.eval('Object.keys(localStorage)'), ['/record2'])


class NoGesturesTest(BrowserTest):
    """No gestures set turns them off: a right-button stroke reaches the page,
    for add-ons with gestures of their own (Gesturefy)."""

    prefs = {'oganesson': {'mouse_gestures': {}}}

    @classmethod
    def setUpClass(cls):
        cls.server = Server({'/a': (200, {'Content-Type': 'text/html'}, PAGE.format(
            'A', '<script>self.seen = []; for (const t of ["pointerdown", "pointermove",'
                 ' "pointerup"]) addEventListener(t, e => e.buttons & 2 || t == "pointerup"'
                 ' ? seen.push(t) : 0); oncontextmenu = e => e.preventDefault();</script>'
            ).encode())})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def test_stroke_reaches_the_page(self):
        page = self.browser.new_tab(self.server.url('/a'))
        wait_for(lambda: page.eval('typeof seen') == 'object', what='the page')
        x, y = self.browser.wait_view('ContentsWebView').center
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '3')
        for step in range(1, 21):
            self.browser.xdotool('mousemove', str(x - step * 8), str(y))
        self.browser.xdotool('mouseup', '3')
        wait_for(lambda: 'pointerup' in page.eval('seen'), what='the stroke in the page')
        seen = page.eval('seen')
        self.assertEqual((seen[0], seen[-1]), ('pointerdown', 'pointerup'))
        self.assertIn('pointermove', seen)


if __name__ == '__main__':
    unittest.main()
