"""What Settings shows: every page in the left menu, and controls that live
on our pages but are easy to lose in a rebase. A patch can still apply while
its markup no longer works (157 turned the menu into Lit, which ignored the
Polymer bindings of restore-autofill-page.patch and hid Autofill), so these
check the rendered page, not the source.
"""

import unittest

from harness import BrowserTest, wait_for
from test_firefox_sync import FIND

# The left menu's entries on Linux, in order.
MENU = ['people', 'appearance', 'autofill', 'privacy', 'performance', 'search',
        'defaultBrowser', 'onStartup', 'languages', 'downloads', 'accessibility',
        'system', 'reset', 'extensionsLink', 'about-menu']

VISIBLE_MENU_ITEMS = f"""(({FIND})('settings-menu').shadowRoot
    .querySelectorAll('a[role=menuitem]'))"""


class SettingsInventoryTest(BrowserTest):

    def test_menu_shows_every_page(self):
        page = self.browser.new_tab('chrome://settings')
        wait_for(lambda: page.eval(f"!!({FIND})('settings-menu')"), what='the settings menu')
        shown = page.eval(f"[...{VISIBLE_MENU_ITEMS}]"
                          ".filter(a => a.getClientRects().length).map(a => a.id)")
        self.assertEqual(shown, MENU)

    def test_crash_reports_on_browser_traffic(self):
        page = self.browser.new_tab('chrome://settings/updates')
        select = (f"({FIND})('settings-browser-traffic')?.shadowRoot"
                  ".querySelector('#crashReportsSelect')")
        wait_for(lambda: page.eval(f"!!{select}?.getClientRects().length"),
                 what='the crash reports row')
        self.assertEqual(page.eval(f"{select}.value"), '-1')
        page.eval(f"{select}.value = '0';"
                  f"{select}.dispatchEvent(new Event('change'))")
        mode = ("import('chrome://resources/js/cr.js').then(cr => "
                "cr.sendWithPromise('getHeliumCrashReporting')).then(s => s.mode)")
        wait_for(lambda: page.eval(mode) == 0, what='crash reports set to ask each time')
        page.eval(f"{select}.value = '-1';"
                  f"{select}.dispatchEvent(new Event('change'))")
        wait_for(lambda: page.eval(mode) == -1, what='crash reports back off')


if __name__ == '__main__':
    unittest.main()
