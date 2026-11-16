"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_cookies_errors.js.

The add-ons' code is Firefox's, but for the container: Firefox's container 1
is Personal, as this browser's first, whose cookieStoreId is
firefox-container-personal. Firefox's firefox-container-99 is a container that
doesn't exist here either."""

from extension_test_utils import JS, FirefoxTest

SETUP = JS(r'''async function background() {
  const url = "http://example.com/";
  const name = "dummyname";
  await browser.cookies.set({ url, name, value: "from_setup:normal" });
  await browser.cookies.set({
    url,
    name,
    value: "from_setup:private",
    storeId: "firefox-private",
  });
  await browser.cookies.set({
    url,
    name,
    value: "from_setup:container",
    storeId: "firefox-container-personal",
  });
  browser.test.sendMessage("setup_done");
}''')

ERROR_MESSAGES = JS(r'''async function background() {
  const url = "http://example.com/";
  const name = "dummyname";
  // Shorthands to minimize boilerplate.
  const set = d => browser.cookies.set({ url, name, value: "x", ...d });
  const remove = d => browser.cookies.remove({ url, name, ...d });
  const get = d => browser.cookies.get({ url, name, ...d });
  const getAll = d => browser.cookies.getAll(d);

  // Host permission permission missing.
  await browser.test.assertRejects(
    set({}),
    /^Permission denied to set cookie \{.*\}$/,
    "cookies.set without host permissions rejects with error"
  );
  browser.test.assertEq(
    null,
    await remove({}),
    "cookies.remove without host permissions does not remove any cookies"
  );
  browser.test.assertEq(
    null,
    await get({}),
    "cookies.get without host permissions does not match any cookies"
  );
  browser.test.assertEq(
    "[]",
    JSON.stringify(await getAll({})),
    "cookies.getAll without host permissions does not match any cookies"
  );

  // Private browsing cookies without access to private browsing mode.
  await browser.test.assertRejects(
    set({ storeId: "firefox-private" }),
    "Extension disallowed access to the private cookies storeId.",
    "cookies.set cannot modify private cookies without permission"
  );
  await browser.test.assertRejects(
    remove({ storeId: "firefox-private" }),
    "Extension disallowed access to the private cookies storeId.",
    "cookies.remove cannot modify private cookies without permission"
  );
  await browser.test.assertRejects(
    get({ storeId: "firefox-private" }),
    "Extension disallowed access to the private cookies storeId.",
    "cookies.get cannot read private cookies without permission"
  );
  await browser.test.assertRejects(
    getAll({ storeId: "firefox-private" }),
    "Extension disallowed access to the private cookies storeId.",
    "cookies.getAll cannot read private cookies without permission"
  );

  // On Android, any firefox-container-... is treated as valid, so it doesn't
  // result in an error. However, because the test extension does not have
  // any host permissions, it will fail with an error any way (but a
  // different one than expected).
  // TODO bug 1743616: Fix implementation and this test.
  const kErrorInvalidContainer = navigator.userAgent.includes("Android")
    ? /Permission denied to set cookie/
    : `Invalid cookie store id: "firefox-container-99"`;

  // Invalid storeId.
  await browser.test.assertRejects(
    set({ storeId: "firefox-container-99" }),
    kErrorInvalidContainer,
    "cookies.set with invalid storeId (non-existent container)"
  );

  await browser.test.assertRejects(
    set({ storeId: "0" }),
    `Invalid cookie store id: "0"`,
    "cookies.set with invalid storeId (format not recognized)"
  );

  for (let method of [remove, get, getAll]) {
    let resultWithInvalidStoreId = method == getAll ? [] : null;
    browser.test.assertEq(
      JSON.stringify(await method({ storeId: "firefox-container-99" })),
      JSON.stringify(resultWithInvalidStoreId),
      `cookies.${method.name} with invalid storeId (non-existent container)`
    );

    browser.test.assertEq(
      JSON.stringify(await method({ storeId: "0" })),
      JSON.stringify(resultWithInvalidStoreId),
      `cookies.${method.name} with invalid storeId (format not recognized)`
    );
  }

  browser.test.sendMessage("test_done");
}''')

FINAL_CHECK = JS(r'''async function background() {
  async function checkCookie(storeId, value) {
    let cookies = await browser.cookies.getAll({ storeId });
    let index = cookies.findIndex(c => c.value === value);
    browser.test.assertTrue(index !== -1, `Found cookie: ${value}`);
    if (index >= 0) {
      cookies.splice(index, 1);
    }
    browser.test.assertEq(
      "[]",
      JSON.stringify(cookies),
      `No more cookies left in cookieStoreId=${storeId}`
    );
  }
  // Added in setup.
  await checkCookie("firefox-default", "from_setup:normal");
  await checkCookie("firefox-private", "from_setup:private");
  await checkCookie("firefox-container-personal", "from_setup:container");
  browser.test.sendMessage("final_check_done");
}''')


class CookiesErrorsTest(FirefoxTest):

    def test_01_setup_cookies(self):
        extension = self.load_extension(
            incognito_override='spanning',
            background=SETUP,
            manifest={'permissions': ['cookies', 'http://example.com/']})
        extension.startup()
        extension.await_message('setup_done')
        extension.unload()

    def test_02_error_messages(self):
        extension = self.load_extension(
            background=ERROR_MESSAGES,
            manifest={'permissions': ['cookies']})
        extension.startup()
        extension.await_message('test_done')
        extension.unload()

    def test_03_expected_cookies_at_end_of_test(self):
        extension = self.load_extension(
            incognito_override='spanning',
            background=FINAL_CHECK,
            manifest={'permissions': ['cookies', '<all_urls>']})
        extension.startup()
        extension.await_message('final_check_done')
        extension.unload()
