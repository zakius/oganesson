"""One toolbar: every button moves anywhere on it, pinned extension
actions and Chrome's pinned buttons alike, and keeps its place on restart.
Customize toolbar hides and shows the built-in items too. Customize toolbar's
reset puts them back. On a fresh profile tab search
is a toolbar button, in either tab strip.
"""

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from harness import WAYLAND, BrowserTest, wait_for

MANIFEST = {'manifest_version': 3, 'name': 'Toolbar test', 'version': '1',
            'action': {'default_title': 'Toolbar test'}}


class ToolbarTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-toolbar-'))
        (cls.folder / 'manifest.json').write_text(json.dumps(MANIFEST))
        cls.browser_args = (f'--load-extension={cls.folder}',)
        # Print: Helium removes Reading list from the pinnable buttons.
        cls.prefs = {'toolbar': {'pinned_actions': ['kActionPrint']}}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def action(self):
        return self.browser.wait_view('ToolbarActionView', match=lambda v: (
            v['TooltipText'] or '').startswith('Toolbar test'))

    def back(self):
        return self.browser.wait_view('BackForwardButton', match=lambda v: (
            v['TooltipText'] or '').startswith('Click to go back'))

    def print_button(self):
        return self.browser.wait_view('PinnedActionToolbarButton', TooltipText='Print')

    def drag(self, view, to_x):
        x, y = view.center
        self.browser.xdotool('mousemove', str(x), str(y), 'mousedown', '1')
        # Paced: the drag starts on a move past the threshold, and the
        # windowing system's drag session must start before the release. A
        # browser slowed by load gets both in one batch, and no drag starts.
        for step in range(1, 11):
            self.browser.xdotool('mousemove', str(x + (to_x - x) * step // 10), str(y))
            time.sleep(0.05)
        self.browser.xdotool('mouseup', '1')

    def order(self):
        """The left-to-right order of the items these tests move."""
        items = {'action': self.action(), 'print': self.print_button(),
                 'reload': self.browser.wait_view('ReloadButton'),
                 'back': self.back(),
                 'location_bar': self.browser.wait_view('LocationBarView')}
        return sorted(items, key=lambda name: items[name].bounds['x'])

    def test_1_pinned_extension_joins_the_toolbar(self):
        settings = self.browser.new_tab('chrome://extensions')
        wait_for(lambda: settings.eval('!!chrome.developerPrivate'), what='chrome://extensions')
        settings.eval("""chrome.developerPrivate.getExtensionsInfo().then(list =>
            chrome.developerPrivate.updateExtensionConfiguration({
              extensionId: list.find(e => e.name === 'Toolbar test').id,
              pinnedToToolbar: true}))""")
        self.browser.close_target(settings)
        # New pinned icons go just before the extensions button.
        puzzle = self.browser.wait_view('ExtensionsToolbarButton')
        self.assertLess(self.action().bounds['x'], puzzle.bounds['x'])

    def test_2_extension_action_moves_left_of_back(self):
        back = self.back()
        self.drag(self.action(), back.bounds['x'])
        wait_for(lambda: self.order()[0] == 'action', what='the action left of back')

    def test_3_built_in_button_moves_past_location_bar(self):
        location = self.browser.wait_view('LocationBarView')
        self.drag(self.browser.wait_view('ReloadButton'),
                  location.bounds['x'] + location.bounds['width'] + 4)
        wait_for(lambda: self.order().index('reload') > self.order().index('location_bar'),
                 what='reload right of the location bar')

    def test_4_chrome_pinned_button_moves_on_its_own(self):
        back = self.back()
        self.drag(self.print_button(), back.bounds['x'] + back.bounds['width'])
        wait_for(lambda: self.order()[:3] == ['action', 'back', 'print'],
                 what='print right after back')

    def test_5_order_survives_restart(self):
        before = self.order()
        self.browser.quit()
        self.browser.start()
        wait_for(lambda: self.order() == before, what=f'the order {before}')

    def test_5b_extensions_button_moves_left_of_back(self):
        # Reset must then put the pinned action back after it, too.
        self.drag(self.browser.wait_view('ExtensionsToolbarButton'), self.back().bounds['x'])
        wait_for(lambda: self.browser.wait_view('ExtensionsToolbarButton').bounds['x']
                 < self.back().bounds['x'], what='the extensions button left of back')

    def test_5c_customize_toolbar_hides_and_shows_back(self):
        page = self.browser.new_tab(
            'chrome://customize-chrome-side-panel.top-chrome/?page=toolbar')
        toggle = r"""(() => { const walk = (root) => { for (const el of root.querySelectorAll('*')) {
            if (el.localName === 'cr-toggle' && el.ariaLabel === 'Back') return el;
            const found = el.shadowRoot && walk(el.shadowRoot); if (found) return found; } };
          return walk(document); })()"""
        wait_for(lambda: page.eval(f'{toggle}?.checked'), what='Back on in Customize toolbar')
        page.eval(f'{toggle}.click()')
        wait_for(lambda: not any(
            v.visible for v in self.browser.views('BackForwardButton')
            if (v['TooltipText'] or '').startswith('Click to go back')), what='Back hidden')
        # The page lists its actions again after each change; a click before
        # that list is in can be lost.
        wait_for(lambda: page.eval(f'{toggle}?.checked') is False, what='Back off in Customize toolbar')
        page.eval(f'{toggle}.click()')
        wait_for(lambda: self.back().visible, what='Back shown again')
        self.browser.close_target(page)

    def test_6_reset_to_default(self):
        page = self.browser.new_tab(
            'chrome://customize-chrome-side-panel.top-chrome/?page=toolbar')
        reset = r"""(() => { const walk = (root) => { for (const el of root.querySelectorAll('*')) {
            if (el.id === 'resetToDefaultButton') return el;
            const found = el.shadowRoot && walk(el.shadowRoot); if (found) return found; } };
          return walk(document); })()"""
        wait_for(lambda: page.eval(f'{reset} && !{reset}.disabled'), what='reset enabled')
        page.eval(f'{reset}.click()')
        # Print is unpinned; the others are back in their places, the
        # extension's action just before the extensions button.
        wait_for(lambda: not any(v.visible for v in self.browser.views(
            'PinnedActionToolbarButton', TooltipText='Print')), what='Print unpinned')

        def order():
            items = {'action': self.action(), 'back': self.back(),
                     'reload': self.browser.wait_view('ReloadButton'),
                     'location_bar': self.browser.wait_view('LocationBarView'),
                     'extensions': self.browser.wait_view('ExtensionsToolbarButton')}
            return sorted(items, key=lambda name: items[name].bounds['x'])

        want = ['back', 'reload', 'location_bar', 'action', 'extensions']
        wait_for(lambda: order() == want, what=f'the order {want}')
        self.browser.close_target(page)


class TabSearchButtonTest(BrowserTest):
    """A fresh profile, horizontal tab strip."""

    def tab_search(self):
        return self.browser.wait_view('PinnedActionToolbarButton', TooltipText='Tab search')

    # Customize toolbar's switch for it.
    TOGGLE = r"""(() => { const walk = (root) => { for (const el of root.querySelectorAll('*')) {
            if (el.localName === 'cr-toggle' && el.ariaLabel === 'Tab search') return el;
            const found = el.shadowRoot && walk(el.shadowRoot); if (found) return found; } };
          return walk(document); })()"""

    def test_1_toolbar_button_size(self):
        # As big as the other toolbar buttons, not in the tab strip.
        button = self.tab_search().bounds
        reload = self.browser.wait_view('ReloadButton').bounds
        self.assertEqual((button['width'], button['height']), (reload['width'], reload['height']))
        self.assertEqual(button['y'], reload['y'])
        self.assertFalse(any(v.visible for v in self.browser.views(
            'TabStripFlatEdgeButton', TooltipText='Tab search')))

    def test_1b_no_media_button(self):
        # It would appear only while media plays; Cast is in the app menu.
        self.tab_search()
        self.assertEqual(self.browser.views('MediaToolbarButtonView'), [])

    def bubbles(self):
        return [v.bounds for v in self.browser.views('WebUIBubbleDialogView') if v.visible]

    def test_2_click_opens_tab_search_under_it(self):
        button = self.tab_search().bounds
        self.browser.click_view(self.tab_search())
        search = self.browser.page('chrome://tab-search.top-chrome')
        wait_for(lambda: search.eval("document.visibilityState == 'visible'"),
                 what='tab search shown')
        # A click on the button closes the bubble only once the bubble is active.
        wait_for(lambda: search.eval('document.hasFocus()'), what='tab search focused')
        # It grows to fit its list, and a click while it grows can be lost.
        bubble = self.browser.wait_settled(
            lambda: [v for v in self.browser.views('WebUIBubbleDialogView') if v.visible],
            what='the tab search bubble')[0].bounds
        # Its top edge on the button's bottom, right edges aligned. With a
        # shadow (always on Wayland, never on Xvfb) the bubble draws a 1 DIP
        # border around these contents, and the border's edges are the ones
        # aligned.
        border = 1 if WAYLAND else 0
        self.assertEqual(bubble['y'] - border, button['y'] + button['height'])
        self.assertEqual(bubble['x'] + bubble['width'] + border, button['x'] + button['width'])

    def test_2b_second_click_closes_it(self):
        self.browser.click_view(self.tab_search())
        wait_for(lambda: not self.bubbles(), what='the tab search bubble closed')

    def test_3_customize_toolbar_unpins_and_pins_it(self):
        page = self.browser.new_tab(
            'chrome://customize-chrome-side-panel.top-chrome/?page=toolbar')
        toggle = self.TOGGLE
        wait_for(lambda: page.eval(f'{toggle}?.checked'), what='Tab search on in Customize toolbar')
        page.eval(f'{toggle}.click()')
        wait_for(lambda: not any(v.visible for v in self.browser.views(
            'PinnedActionToolbarButton', TooltipText='Tab search')), what='Tab search unpinned')
        wait_for(lambda: page.eval(f'{toggle}.checked === false'), what='its switch off')
        page.eval(f'{toggle}.click()')
        self.tab_search()
        self.browser.close_target(page)


class VerticalTabSearchButtonTest(TabSearchButtonTest):
    """The same with the vertical tab strip."""
    prefs = {'helium': {'browser': {'layout': 2}}}  # Helium's vertical layout


if __name__ == '__main__':
    unittest.main()
