"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_cookies_expiry.html.

The add-on's background is Firefox's, as it is. The test's cookies, which
Firefox adds with Gecko's cookie service, come from DevTools in a tab's own
store (head_cookies.py)."""

import time

from extension_test_utils import JS, FirefoxTest
from firefox.head_cookies import CookieService

BACKGROUND = JS(r'''function background() {
    let expectedEvents = [];

    browser.cookies.onChanged.addListener(event => {
      expectedEvents.push(`${event.removed}:${event.cause}`);
      if (expectedEvents.length === 1) {
        browser.test.assertEq("true:expired", expectedEvents[0], "expired cookie removed");
        browser.test.assertEq("first", event.cookie.name, "expired cookie has the expected name");
        browser.test.assertEq("one", event.cookie.value, "expired cookie has the expected value");
      } else {
        browser.test.assertEq("false:explicit", expectedEvents[1], "new cookie added");
        browser.test.assertEq("first", event.cookie.name, "new cookie has the expected name");
        browser.test.assertEq("one-again", event.cookie.value, "new cookie has the expected value");
        browser.test.notifyPass("cookie-expiry");
      }
    });

    setTimeout(() => {
      browser.test.sendMessage("change-cookies");
    }, 1000);
  }''')


class CookiesExpiryTest(FirefoxTest):

    def test_01_cookies_expiry(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['http://example.com/', 'cookies'],
            },
            background=BACKGROUND)

        page = self.open_tab('about:blank')
        try:
            cookies = CookieService(page)
            cookies.add('.example.com', '/', 'first', 'one', False, False, False,
                        time.time() * 1000 + 1000)

            extension.startup()
            extension.await_message('change-cookies')

            cookies.add('.example.com', '/', 'first', 'one-again', False, False, False,
                        time.time() * 1000 + 10000)
        finally:
            self.browser.close_target(page)

        extension.await_finish('cookie-expiry')
        extension.unload()
