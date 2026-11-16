"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_cookies_incognito.html.

The add-ons' code is Firefox's, as it is. The test's cookies, which Firefox
adds with Gecko's cookie service, come from DevTools in a tab's own store
(head_cookies.py): a tab of a private window for the private cookie."""

import random

from extension_test_utils import JS, FirefoxTest
from firefox.head_cookies import CookieService
from harness import Page, wait_for

# JavaScript's Number.MAX_SAFE_INTEGER, the cookies' expiry in Firefox's test.
MAX_SAFE_INTEGER = 2 ** 53 - 1

PRIVATE_BACKGROUND = JS(r'''async function background() {
      let window = await browser.windows.create({incognito: true});
      browser.test.onMessage.addListener(async () => {
        await browser.windows.remove(window.id);
        browser.test.sendMessage("done");
      });
      browser.test.sendMessage("ready");
    }''')

BACKGROUND = JS(r'''async function background() {
    const storeId = "firefox-private";
    const url = "http://example.org/";

    // Getting the wrong storeId will fail, otherwise we should finish the test fine.
    browser.cookies.onChanged.addListener(changeInfo => {
      let {cookie} = changeInfo;
      browser.test.assertTrue(cookie.storeId != storeId, "cookie store is correct");
    });

    browser.test.onMessage.addListener(async () => {
      let stores = await browser.cookies.getAllCookieStores();
      let store = stores.find(s => s.incognito);
      browser.test.assertTrue(!store, "incognito cookie store should not be available");
      browser.test.notifyPass("cookies");
    });

    await browser.test.assertRejects(
      browser.cookies.set({url, name: "test", storeId}),
      /Extension disallowed access/,
      "API should reject setting cookie");
    await browser.test.assertRejects(
      browser.cookies.get({url, name: "test", storeId}),
      /Extension disallowed access/,
      "API should reject getting cookie");
    await browser.test.assertRejects(
      browser.cookies.getAll({url, storeId}),
      /Extension disallowed access/,
      "API should reject getting cookie");
    await browser.test.assertRejects(
      browser.cookies.remove({url, name: "test", storeId}),
      /Extension disallowed access/,
      "API should reject getting cookie");
    await browser.test.assertRejects(
      browser.cookies.getAll({url, storeId}),
      /Extension disallowed access/,
      "API should reject getting cookie");

    browser.test.sendMessage("set-cookies");
  }''')


class CookiesIncognitoTest(FirefoxTest):

    def private_tab(self):
        """A tab of a new private window."""
        before = {t['id'] for t in self.browser.targets()}
        self.browser.key('ctrl+shift+n')
        return Page(wait_for(lambda: next((t for t in self.browser.targets()
                                           if t['id'] not in before and t['type'] == 'page'),
                                          None), what='the private window'))

    def test_01_cookies_incognito_not_allowed(self):
        private_extension = self.load_extension(
            incognito_override='spanning',
            background=PRIVATE_BACKGROUND,
            manifest={
                'permissions': ['cookies', '*://example.org/'],
            })
        private_extension.startup()
        private_extension.await_message('ready')

        extension = self.load_extension(
            background=BACKGROUND,
            manifest={
                'permissions': ['cookies', '*://example.org/'],
            })
        extension.startup()
        extension.await_message('set-cookies')

        public, private = self.open_tab('about:blank'), self.private_tab()
        try:
            for page, name in ((public, 'public'), (private, 'private')):
                CookieService(page).add('example.org', '/', name, f'foo{random.random()}',
                                        False, False, False, MAX_SAFE_INTEGER)
        finally:
            self.browser.close_target(public)
            self.browser.close_target(private)

        extension.send_message('test-cookie-store')
        extension.await_finish('cookies')
        extension.unload()
        private_extension.send_message('close')
        private_extension.await_message('done')
        private_extension.unload()
