"""oganesson's setup, chrome://settings/setup
(oganesson/settings/setup-page.patch): a first run opens it with every step;
later starts open it with only the new choice until browser traffic is chosen
once, and never after.

These tests run without --no-first-run, which skips setup.
"""

import json
import unittest

from harness import BrowserTest, wait_for
from test_firefox_sync import FIND

STEP = ("document.querySelector('settings-ui')?.shadowRoot?"
        ".querySelector('settings-setup-page')")
BLOCKER_WARNING = (f"{STEP}.shadowRoot.querySelector('#traffic').shadowRoot"
                   ".querySelector('#blockerWarning')")


class SetupTest(BrowserTest):
    first_run = True

    def setup_page(self):
        return self.browser.page('chrome://settings/setup', timeout=30)

    def steps(self, page):
        return page.eval(f"{STEP}.steps_.map(step => step.id)")

    def click(self, page, button):
        page.eval(f"{STEP}.shadowRoot.querySelector('#{button}').click()")

    def test_1_first_run_shows_every_step(self):
        page = self.setup_page()
        wait_for(lambda: page.eval(f"!!{STEP}?.steps_"), what='the setup page')
        self.assertEqual(self.steps(page), [
            'welcome', 'import', 'sync', 'traffic', 'google', 'search', 'tabs', 'passwords',
            'privacy', 'default', 'done'])
        self.assertTrue(page.eval(f"{STEP}.shadowRoot.querySelector('#skip').hidden"))
        self.click(page, 'next')
        # Import and Sync can be skipped; Browser traffic can't.
        for _ in range(2):
            wait_for(lambda: not page.eval(f"{STEP}.shadowRoot.querySelector('#skip').hidden"),
                     what='Skip')
            self.click(page, 'skip')
        wait_for(lambda: page.eval(f"{STEP}.step_") == 'traffic', what='Browser traffic')
        self.assertTrue(page.eval(f"{STEP}.shadowRoot.querySelector('#skip').hidden"))
        # Through my server needs a server that answered: Next waits.
        page.eval("chrome.send('applyBrowserTrafficPreset', ['throughServer'])")
        wait_for(lambda: page.eval(f"{STEP}.shadowRoot.querySelector('#next').disabled"),
                 what='Next disabled without a server')
        # uBO's lists come only through the server then: setup says what
        # that means when it can't be reached.
        wait_for(lambda: page.eval(f"!!{BLOCKER_WARNING}"), what='the content blocker warning')
        page.eval("chrome.send('applyBrowserTrafficPreset', ['direct'])")
        wait_for(lambda: not page.eval(f"{STEP}.shadowRoot.querySelector('#next').disabled"),
                 what='Next enabled for Direct')
        wait_for(lambda: not page.eval(f"!!{BLOCKER_WARNING}"),
                 what='no content blocker warning for Direct')
        self.click(page, 'next')
        wait_for(lambda: page.eval(f"{STEP}.step_") == 'google', what='Google features')
        # Every Google opt-in starts off; turning one on here turns it on in
        # Settings.
        toggle = f"{STEP}.shadowRoot.querySelector('#{{}}')"
        wait_for(lambda: page.eval(f"!!{toggle.format('googleLens')}"), what='the switches')
        for name in ('googleLens', 'translatePages'):
            self.assertIs(page.eval(f"{toggle.format(name)}.checked"), False)
        self.assertTrue(page.eval(f"{toggle.format('translateEngine')}.hidden"))
        page.eval(f"{toggle.format('googleLens')}.click()")
        page.eval(f"{toggle.format('translatePages')}.click()")
        wait_for(lambda: not page.eval(f"{toggle.format('translateEngine')}.hidden"),
                 what='the translation engines')
        page.eval(f"{toggle.format('translateEngine')}.querySelectorAll('.card')[1].click()")
        get = "chrome.settingsPrivate.getPref('{}').then(p => p.value)"
        wait_for(lambda: page.eval(get.format('oganesson.translate.engine')) == 'google',
                 what='the engine pref')
        self.click(page, 'next')
        wait_for(lambda: page.eval(f"{STEP}.step_") == 'search', what='Search')

        settings = self.browser.new_tab('chrome://settings/search')
        lens = (f"({FIND})('settings-search-page')?.shadowRoot"
                "?.querySelector('#googleLens')")
        wait_for(lambda: settings.eval(f'!!{lens}'), what='the Lens switch')
        wait_for(lambda: settings.eval(f'{lens}.checked') is True, what='Lens on in Settings')
        self.browser.close_target(settings)
        settings = self.browser.new_tab('chrome://settings/languages')
        translate = f"({FIND})('settings-translate-page')?.shadowRoot"
        wait_for(lambda: settings.eval(f'!!{translate}?.querySelector("#translatePages")'),
                 what='the translation switch')
        wait_for(lambda: settings.eval(
            f'{translate}.querySelector("#translatePages").checked') is True,
            what='translation on in Settings')
        wait_for(lambda: settings.eval(
            f'{translate}.querySelector("controlled-radio-button[name=google]").checked') is True,
            what='Google Translate picked in Settings')
        self.browser.close_target(settings)

    def test_2_later_starts_show_only_the_new_choice(self):
        self.browser.quit()
        path = self.browser.profile / 'Local State'
        state = json.loads(path.read_text())
        self.assertTrue(state['browser_traffic']['chosen'])
        state['browser_traffic']['chosen'] = False
        path.write_text(json.dumps(state))
        self.browser.start()
        page = self.browser.page('chrome://settings/setup?existing', timeout=30)
        wait_for(lambda: page.eval(f"!!{STEP}?.steps_"), what='the setup page')
        self.assertEqual(self.steps(page), ['welcome', 'traffic', 'done'])
        self.click(page, 'next')
        wait_for(lambda: page.eval(f"{STEP}.step_") == 'traffic', what='Browser traffic')
        self.click(page, 'next')
        wait_for(lambda: page.eval(f"{STEP}.step_") == 'done', what='Done')

    def test_3_chosen_starts_open_no_setup(self):
        self.browser.quit()
        self.browser.start()
        self.assertFalse(any('settings/setup' in t['url'] for t in self.browser.targets()))


if __name__ == '__main__':
    unittest.main()
