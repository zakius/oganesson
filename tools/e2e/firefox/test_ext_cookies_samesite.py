"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_cookies_samesite.js.

The add-on's code is Firefox's, as it is. Firefox's test turns off two of its
cookie rules with prefs, because its test server has no HTTPS. This browser has
no setting for either. network.cookie.sameSite.laxByDefault off: Chromium
treats a cookie without SameSite as Lax too, but the cookies API gives its
sameSite as "unspecified", as the test expects. network.cookie.sameSite.
noneRequiresSecure off: Chromium always refuses a SameSite=None cookie that
isn't Secure, as Firefox does by default. So test4 isn't set, and the
add-on's background stops where it reads test4's sameSite: the checks after it
(getAll, and set() with each sameSite, whose "no_restriction" Chromium refuses
by the same rule) don't run. The port fails by that rule, not on a missing part
of the API."""

from extension_test_utils import JS, FirefoxTest

CONTENT_SCRIPT = JS(r'''function contentScript() {
  document.cookie = "test1=whatever";
  document.cookie = "test2=whatever; SameSite=lax";
  document.cookie = "test3=whatever; SameSite=strict";
  document.cookie = "test4=whatever; SameSite=none";
  browser.runtime.sendMessage("do-check-cookies");
}''')

BACKGROUND = JS(r'''async function background() {
  await new Promise(resolve => {
    browser.runtime.onMessage.addListener(msg => {
      browser.test.assertEq("do-check-cookies", msg, "expected message");
      resolve();
    });
  });

  const url = "https://example.org/";

  // Baseline. Every cookie must have the expected sameSite.
  let cookie = await browser.cookies.get({ url, name: "test1" });
  browser.test.assertEq(
    "unspecified",
    cookie.sameSite,
    "Expected sameSite for test1"
  );

  cookie = await browser.cookies.get({ url, name: "test2" });
  browser.test.assertEq(
    "lax",
    cookie.sameSite,
    "Expected sameSite for test2"
  );

  cookie = await browser.cookies.get({ url, name: "test3" });
  browser.test.assertEq(
    "strict",
    cookie.sameSite,
    "Expected sameSite for test3"
  );

  cookie = await browser.cookies.get({ url, name: "test4" });
  browser.test.assertEq(
    "no_restriction",
    cookie.sameSite,
    "Expected sameSite for test4"
  );

  // Testing cookies.getAll + cookies.set
  let cookies = await browser.cookies.getAll({ url, name: "test3" });
  browser.test.assertEq(1, cookies.length, "There is only one test3 cookie");

  cookie = await browser.cookies.set({
    url,
    name: "test3",
    value: "newvalue",
  });
  browser.test.assertEq(
    "unspecified",
    cookie.sameSite,
    "sameSite defaults to unspecified"
  );

  for (let sameSite of ["unspecified", "no_restriction", "lax", "strict"]) {
    cookie = await browser.cookies.set({ url, name: "test3", sameSite });
    browser.test.assertEq(
      sameSite,
      cookie.sameSite,
      `Expected sameSite=${sameSite} in return value of cookies.set`
    );
    cookies = await browser.cookies.getAll({ url, name: "test3" });
    browser.test.assertEq(
      1,
      cookies.length,
      `test3 is still the only cookie after setting sameSite=${sameSite}`
    );
    browser.test.assertEq(
      sameSite,
      cookies[0].sameSite,
      `test3 was updated to sameSite=${sameSite}`
    );
  }

  browser.test.notifyPass("cookies");
}''')


class CookiesSameSiteTest(FirefoxTest):
    hosts = ('example.org',)
    routes = {'/sameSiteCookiesApiTest': (200, {'Content-Type': 'text/html; charset=utf-8'},
                                          b'<!DOCTYPE html><html></html>')}

    def test_01_samesite_cookies(self):
        extension = self.load_extension(
            background=BACKGROUND,
            manifest={
                'permissions': ['cookies', '*://example.org/'],
                'content_scripts': [{
                    'matches': ['*://example.org/sameSiteCookiesApiTest*'],
                    'js': ['contentscript.js'],
                }],
            },
            files={'contentscript.js': CONTENT_SCRIPT})
        extension.startup()
        page = self.open_tab('http://example.org/sameSiteCookiesApiTest')
        extension.await_finish('cookies')
        self.browser.close_target(page)
        extension.unload()
