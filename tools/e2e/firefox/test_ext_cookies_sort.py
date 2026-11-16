"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_cookies_sort.js.

The add-on's code is Firefox's, as it is."""

from extension_test_utils import JS, FirefoxTest

CONTENT_SCRIPT = JS(r'''function contentScript() {
  document.cookie = "a=1; path=/";
  document.cookie = "a=3; path=/sub/dir";
  document.cookie = "a=4; path=/sub/dir/deeper";
  document.cookie = "a=2; path=/sub";
  browser.runtime.sendMessage("do-check-cookies");
}''')

BACKGROUND = JS(r'''async function background() {
  await new Promise(resolve => {
    browser.runtime.onMessage.addListener(msg => {
      browser.test.assertEq("do-check-cookies", msg, "expected message");
      resolve();
    });
  });

  const cookies = await browser.cookies.getAll({ name: "a" });
  // Cookies should be sorted according to RFC 6256, like document.cookie.
  browser.test.assertEq(4, cookies.length, "4 cookies expected");
  browser.test.assertEq("4", cookies[0].value, "4");
  browser.test.assertEq("3", cookies[1].value, "3");
  browser.test.assertEq("2", cookies[2].value, "2");
  browser.test.assertEq("1", cookies[3].value, "1");

  const cookie = await browser.cookies.get({
    name: "a",
    url: "https://example.org/sub/dir",
  });
  browser.test.assertEq("/sub/dir", cookie?.path, "Expected exact path");

  browser.test.notifyPass("cookies");
}''')


class CookiesSortTest(FirefoxTest):
    hosts = ('example.org',)
    routes = {'/sortCookies': (200, {'Content-Type': 'text/html; charset=utf-8'},
                               b'<!DOCTYPE html><html></html>')}

    def test_01_same_cookie_name_with_multiple_paths(self):
        extension = self.load_extension(
            background=BACKGROUND,
            manifest={
                'permissions': ['cookies', '*://example.org/'],
                'content_scripts': [{
                    'matches': ['*://example.org/sortCookies*'],
                    'js': ['contentscript.js'],
                }],
            },
            files={'contentscript.js': CONTENT_SCRIPT})
        extension.startup()
        page = self.open_tab('http://example.org/sortCookies')
        extension.await_finish('cookies')
        self.browser.close_target(page)
        extension.unload()
