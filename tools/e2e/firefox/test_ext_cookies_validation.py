"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_cookies_validation.js.

The add-ons' code is Firefox's, as it is. Firefox's pref
network.cookie.valueless_cookie has no equal in this browser, which always
takes a cookie without a name, as Firefox does with the pref off: the expected
error for a nameless cookie is the one for the pref off, the task that turns it
on (test_nameless_cookie_rejected_with_valueless_pref_on) is left out, and the
one that turns it off runs as it is."""

import json

from extension_test_utils import JS, FirefoxTest

INVALID_COOKIES = JS(r'''async function backgroundScript() {
  browser.test.onMessage.addListener(async message => {
    let failure = true;
    try {
      await browser.cookies.set({
        url: "https://example.com",
        ...message.cookie,
      });
      failure = false;
    } catch (e) {
      browser.test.assertEq(
        e.message,
        message.errorString,
        `${message.title} - correct exception`
      );
    } finally {
      browser.test.assertTrue(failure, message.title);
      browser.test.sendMessage("completed");
    }
  });

  browser.test.sendMessage("ready");
}''')

# The nameless cookie's error with network.cookie.valueless_cookie off.
NAMELESS_ERROR = 'Cookie “” has been rejected for invalid prefix.'

# Firefox's list of invalid cookies, which JavaScript builds.
TESTS = JS(r'''(namelessError) => [
  {
    cookie: {},
    title: "Unset name and value",
    errorString:
      "Cookie with an empty name and an empty value has been rejected.",
  },
  {
    cookie: { name: "" },
    title: "Empty name and unset value",
    errorString:
      "Cookie with an empty name and an empty value has been rejected.",
  },
  {
    cookie: { value: "" },
    title: "Unset name and empty value",
    errorString:
      "Cookie with an empty name and an empty value has been rejected.",
  },
  {
    cookie: { name: "", value: "" },
    title: "Empty name and value",
    errorString:
      "Cookie with an empty name and an empty value has been rejected.",
  },
  {
    cookie: { name: "a".repeat(3000), value: "a".repeat(3000) },
    title: "Name/value oversize",
    errorString: `Cookie “${"a".repeat(3000)}” is invalid because its size is too big. Max size is 4096 B.`,
  },
  {
    cookie: { name: ";", value: "a" },
    title: "Invalid chars in the name",
    errorString:
      "Cookie “;” has been rejected for invalid characters in the name.",
  },
  {
    cookie: { name: " ", value: "a" },
    title: "Invalid chars in the name (2)",
    errorString:
      "Cookie “ ” has been rejected for invalid characters in the name.",
  },
  {
    cookie: { name: "a", value: ";" },
    title: "Invalid chars in the value",
    errorString:
      "Cookie “a” has been rejected for invalid characters in the value.",
  },
  {
    cookie: { name: "a", value: " " },
    title: "Invalid chars in the value (2)",
    errorString:
      "Cookie “a” has been rejected for invalid characters in the value.",
  },
  {
    cookie: { name: "", value: "__Secure-wow" },
    title: "Invalid prefix (__Secure)",
    errorString: namelessError,
  },
  {
    cookie: { name: "", value: "__Host-wow" },
    title: "Invalid prefix (__Host)",
    errorString: namelessError,
  },
  {
    cookie: { name: "a", value: "b", sameSite: "no_restriction" },
    title: "None requires secure",
    errorString:
      "Cookie “a” rejected because it has the “SameSite=None” attribute but is missing the “secure” attribute.",
  },
  {
    cookie: { name: "a", value: "b", path: "a".repeat(1025) },
    title: "Path oversize",
    errorString:
      "Cookie “a” has been rejected because its path attribute is too big.",
  },
  {
    cookie: {
      url: "https://example..com",
      domain: ".example.com",
      name: "test",
    },
    title: "Invalid url",
    errorString: `Invalid domain url: "https://example..com"`,
    failure: true,
  },
  {
    cookie: {
      url: "https://example..com",
      name: "test",
    },
    title: "Invalid url and no domain",
    errorString: `Invalid domain: "example..com"`,
    failure: true,
  },
]''')

VALUELESS_PREF_OFF = JS(r'''async function backgroundScript() {
  const TEST_URL = "https://example.com";
  let cookie = await browser.cookies.set({ value: "dummy", url: TEST_URL });
  browser.test.assertEq("", cookie.name, "default name set");
  browser.test.assertEq("dummy", cookie.value, "dummy value set");
  browser.test.assertEq(
    true,
    cookie.session,
    "no expiry date created session cookie"
  );

  const details = await browser.cookies.remove({ url: TEST_URL, name: "" });
  browser.test.assertEq(TEST_URL, details.url, "removed cookie url");
  browser.test.assertEq("", details.name, "removed cookie name");

  browser.test.sendMessage("done");
}''')


class CookiesValidationTest(FirefoxTest):

    def test_01_do_test_invalid_cookies(self):
        extension = self.load_extension(
            background=INVALID_COOKIES,
            manifest={
                'permissions': [
                    'cookies',
                    'https://example.com/*',
                    'https://example..com/*',
                ],
            })
        extension.startup()
        extension.await_message('ready')
        page = self.open_tab('about:blank')
        tests = page.eval(str(JS(TESTS.source, json.dumps(NAMELESS_ERROR))))
        self.browser.close_target(page)
        for test in tests:
            extension.send_message(test)
            extension.await_message('completed')
        extension.unload()

    def test_03_nameless_cookie_with_valueless_pref_off(self):
        extension = self.load_extension(
            background=VALUELESS_PREF_OFF,
            manifest={'permissions': ['cookies', 'https://example.com/*']})
        extension.startup()
        extension.await_message('done')
        extension.unload()
