"""The "Show close buttons on tabs" setting (docs/tab-behavior.md).

The active tab shows its close button by default. The switch on Settings >
Appearance hides it in open tabs and shows it again. The same holds for
vertical tabs.
"""

import json
import unittest

from harness import BrowserTest, wait_for
from test_firefox_sync import FIND

PREF = 'oganesson.tabs.show_close_buttons'


class TabCloseButtonsTest(BrowserTest):

    def close_buttons(self):
        return [v for v in self.browser.views('TabCloseButton') if v.visible]

    def test_switch_hides_close_buttons_in_open_tabs(self):
        wait_for(self.close_buttons, what='a close button')
        page = self.browser.new_tab('chrome://settings/appearance')
        try:
            toggle = (f"({FIND})('settings-appearance-page')?.shadowRoot"
                      "?.querySelector('#showTabCloseButtons')")
            wait_for(lambda: page.eval(f'!!{toggle}'), what='the switch')
            self.assertEqual(page.eval(f'{toggle}.label'), 'Show close buttons on tabs')
            get = f'chrome.settingsPrivate.getPref({json.dumps(PREF)}).then(p => p.value)'
            self.assertIs(page.eval(f'{toggle}.checked'), True)
            page.eval(f'{toggle}.click()')
            wait_for(lambda: page.eval(get) is False, what='the pref off')
            wait_for(lambda: not self.close_buttons(), what='the close buttons to go')
            page.eval(f'{toggle}.click()')
            wait_for(lambda: page.eval(get) is True, what='the pref on')
            wait_for(self.close_buttons, what='the close button back')
        finally:
            self.browser.close_target(page)


class VerticalTabsTest(TabCloseButtonsTest):
    prefs = {'helium': {'browser': {'layout': 2}}}  # Helium's vertical layout


if __name__ == '__main__':
    unittest.main()
