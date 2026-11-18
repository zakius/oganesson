"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_privacy_nonPersistentCookies.js.

promiseConsoleOutput() collects Gecko's console messages while the add-on
runs; here they are the add-on's errors and console messages
(Browser.extension_errors(): chrome://extensions' warnings and errors, and the
add-on's console lines in the browser's log), read before the unload, since
chrome://extensions forgets a removed add-on. AddonTestUtils.checkMessages()
is a check that the expected messages come, in order, among the others.

Left out: AddonTestUtils' start and stop of Gecko's add-on manager, and its
overrideCertDB(). The add-on's code is Firefox's, as it is."""

import re

from extension_test_utils import JS, FirefoxTest


class NonPersistentCookiesTest(FirefoxTest):
    def test_01_nonPersistentCookies_is_deprecated(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['privacy'],
            },
            use_addon_manager='temporary',
            background=JS('''async function background() {
      for (const nonPersistentCookies of [true, false]) {
        await browser.privacy.websites.cookieConfig.set({
          value: {
            behavior: "reject_third_party",
            nonPersistentCookies,
          },
        });
      }

      browser.test.sendMessage("background-done");
    }'''))

        extension.startup()
        extension.await_message('background-done')
        messages = self.browser.extension_errors(extension.id)
        extension.unload()

        expected_message = r'''"'nonPersistentCookies' has been deprecated and it has no effect anymore."'''

        expected = [expected_message, expected_message]
        for message in messages:
            if expected and re.search(expected[0], message):
                expected.pop(0)
        self.is_(expected, [], f'the expected messages are logged - Messages: {messages}')
