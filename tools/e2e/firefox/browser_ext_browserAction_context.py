"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_browserAction_context.js.

Firefox reads its toolbar widget's `tooltiptext`, `label`, `image`,
`disabled` and `badge`; here they are the add-on's toolbar button, pinned,
in the newest window, the window of the test's active tab
(head.action_button_state()). The button has no label: its title is its
tooltip, and the port reads the tooltip for both. Firefox reads the icon's
URL, and its images are all one image; the button has no URL, so the port
gives each image file a colour of its own (IMAGES) and reads which one the
button shows. Firefox's generic icon is an icon of none of these colours.
This browser shows a disabled action with a grey icon, and its button can
still be clicked. The badge's text is painted on the button and can't be
read: the port checks that a badge shows when the text isn't empty, and
reads its colours as pixels. A badge colour's alpha isn't read.

testNavigationClearsData's example.com is a local server here, and its
about:newtab is this browser's new tab page. Left out: requestLongerTimeout()
and promiseAnimationFrame(), Gecko internals; tabTracker.getId(), Gecko's
map of tabs to IDs, is the ID the add-on reads for the active tab
(head.active_tab_id()). The add-ons' code is Firefox's, as it is.
"""

import json

from firefox import head
from extension_test_utils import JS, FirefoxTest
from harness import wait_for
from test_importer import png

# Each image file's colour: saturated, and with a grey (head.greyed())
# that differs from the other images' of its test.
IMAGES = {
    'default.png': (255, 0, 0),
    '1.png': (0, 128, 0),
    '2.png': (0, 0, 160),
    'global.png': (255, 128, 128),
    'global2.png': (160, 255, 160),
    'window.png': (64, 0, 0),
    'tab.png': (0, 96, 96),
    'window1.png': (128, 0, 128),
    'window2.png': (0, 96, 192),
    'icon.png': (192, 96, 0),
}

BACKGROUND = r'''async function background(getTests) {
  let manifest = browser.runtime.getManifest();
  let { manifest_version } = manifest;
  const action = manifest_version < 3 ? "browserAction" : "action";
  async function checkExtAPIDetails(expecting, details) {
    let title = await browser[action].getTitle(details);
    browser.test.assertEq(
      expecting.title,
      title,
      "expected value from getTitle"
    );

    let popup = await browser[action].getPopup(details);
    browser.test.assertEq(
      expecting.popup,
      popup,
      "expected value from getPopup"
    );

    let badge = await browser[action].getBadgeText(details);
    browser.test.assertEq(
      expecting.badge,
      badge,
      "expected value from getBadge"
    );

    let badgeBackgroundColor =
      await browser[action].getBadgeBackgroundColor(details);
    browser.test.assertEq(
      String(expecting.badgeBackgroundColor),
      String(badgeBackgroundColor),
      "expected value from getBadgeBackgroundColor"
    );

    let badgeTextColor = await browser[action].getBadgeTextColor(details);
    browser.test.assertEq(
      String(expecting.badgeTextColor),
      String(badgeTextColor),
      "expected value from getBadgeTextColor"
    );

    let enabled = await browser[action].isEnabled(details);
    browser.test.assertEq(
      expecting.enabled,
      enabled,
      "expected value from isEnabled"
    );

    // Test signature with (optional) tabId.
    // An optional (undefined) tabId is equivalent to an empty object.
    if (Object.keys(details).length === 0 || "tabId" in details) {
      let enabledByTabId = await browser[action].isEnabled(details.tabId);
      browser.test.assertEq(
        expecting.enabled,
        enabledByTabId,
        "expected value from isEnabled with tabId argument type"
      );
    }
  }

  let tabs = [];
  let windows = [];
  let tests = getTests(tabs, windows);

  {
    let tabId = 0xdeadbeef;
    let calls = [
      () => browser[action].enable(tabId),
      () => browser[action].disable(tabId),
      () => browser[action].setTitle({ tabId, title: "foo" }),
      () => browser[action].setIcon({ tabId, path: "foo.png" }),
      () => browser[action].setPopup({ tabId, popup: "foo.html" }),
      () => browser[action].setBadgeText({ tabId, text: "foo" }),
      () =>
        browser[action].setBadgeBackgroundColor({
          tabId,
          color: [0xff, 0, 0, 0xff],
        }),
      () =>
        browser[action].setBadgeTextColor({
          tabId,
          color: [0, 0xff, 0xff, 0xff],
        }),
    ];

    for (let call of calls) {
      await browser.test.assertRejects(
        new Promise(resolve => resolve(call())),
        RegExp(`Invalid tab ID: ${tabId}`),
        "Expected invalid tab ID error"
      );
    }
  }

  // Runs the next test in the `tests` array, checks the results,
  // and passes control back to the outer test scope.
  function nextTest() {
    let test = tests.shift();

    test(async (expectTab, expectWindow, expectGlobal, expectDefault) => {
      expectGlobal = { ...expectDefault, ...expectGlobal };
      expectWindow = { ...expectGlobal, ...expectWindow };
      expectTab = { ...expectWindow, ...expectTab };

      // Check that the API returns the expected values, and then
      // run the next test.
      let [{ windowId, id: tabId }] = await browser.tabs.query({
        active: true,
        currentWindow: true,
      });
      await checkExtAPIDetails(expectTab, { tabId });
      await checkExtAPIDetails(expectWindow, { windowId });
      await checkExtAPIDetails(expectGlobal, {});

      // Check that the actual icon has the expected values, then
      // run the next test.
      browser.test.sendMessage("nextTest", expectTab, windowId, tests.length);
    });
  }

  browser.test.onMessage.addListener(msg => {
    if (msg != "runNextTest") {
      browser.test.fail("Expecting 'runNextTest' message");
    }

    nextTest();
  });

  let [{ id, windowId }] = await browser.tabs.query({
    active: true,
    currentWindow: true,
  });
  tabs.push(id);
  windows.push(windowId);
  nextTest();
}'''

TAB_SWITCH_TESTS = r'''function (tabs) {
  let manifest = browser.runtime.getManifest();
  let { manifest_version } = manifest;
  const action = manifest_version < 3 ? "browserAction" : "action";

  let details = [
    {
      icon: browser.runtime.getURL("default.png"),
      popup: browser.runtime.getURL("default.html"),
      title: "Default Title",
      badge: "",
      badgeBackgroundColor: [0xd9, 0, 0, 255],
      badgeTextColor: [0xff, 0xff, 0xff, 0xff],
      enabled: true,
    },
    { icon: browser.runtime.getURL("1.png") },
    {
      icon: browser.runtime.getURL("2.png"),
      popup: browser.runtime.getURL("2.html"),
      title: "Title 2",
      badge: "2",
      badgeBackgroundColor: [0xff, 0, 0, 0xff],
      badgeTextColor: [0, 0xff, 0xff, 0xff],
      enabled: false,
    },
    {
      icon: browser.runtime.getURL("global.png"),
      popup: browser.runtime.getURL("global.html"),
      title: "Global Title",
      badge: "g",
      badgeBackgroundColor: [0, 0xff, 0, 0xff],
      badgeTextColor: [0xff, 0, 0xff, 0xff],
      enabled: false,
    },
    {
      icon: browser.runtime.getURL("global.png"),
      popup: browser.runtime.getURL("global.html"),
      title: "Global Title",
      badge: "g",
      badgeBackgroundColor: [0, 0xff, 0, 0xff],
      badgeTextColor: [0xff, 0, 0xff, 0xff],
    },
  ];

  let promiseTabLoad = details => {
    return new Promise(resolve => {
      browser.tabs.onUpdated.addListener(function listener(tabId, changed) {
        if (tabId == details.id && changed.url == details.url) {
          browser.tabs.onUpdated.removeListener(listener);
          resolve();
        }
      });
    });
  };

  return [
    async expect => {
      browser.test.log("Initial state, expect default properties.");

      expect(null, null, null, details[0]);
    },
    async expect => {
      browser.test.log(
        "Change the icon in the current tab. Expect default properties excluding the icon."
      );
      browser[action].setIcon({ tabId: tabs[0], path: "1.png" });

      expect(details[1], null, null, details[0]);
    },
    async expect => {
      browser.test.log("Create a new tab. Expect default properties.");
      let tab = await browser.tabs.create({
        active: true,
        url: "about:blank?0",
      });
      tabs.push(tab.id);

      browser.test.log("Await tab load.");
      let promise = promiseTabLoad({ id: tabs[1], url: "about:blank?0" });
      let { url } = await browser.tabs.get(tabs[1]);
      if (url === "about:blank") {
        await promise;
      }

      expect(null, null, null, details[0]);
    },
    async expect => {
      browser.test.log("Change properties. Expect new properties.");
      let tabId = tabs[1];
      browser[action].setIcon({ tabId, path: "2.png" });
      browser[action].setPopup({ tabId, popup: "2.html" });
      browser[action].setTitle({ tabId, title: "Title 2" });
      browser[action].setBadgeText({ tabId, text: "2" });
      browser[action].setBadgeBackgroundColor({
        tabId,
        color: "#ff0000",
      });
      browser[action].setBadgeTextColor({ tabId, color: "#00ffff" });
      browser[action].disable(tabId);

      expect(details[2], null, null, details[0]);
    },
    async expect => {
      browser.test.log(
        "Switch back to the first tab. Expect previously set properties."
      );
      await browser.tabs.update(tabs[0], { active: true });
      expect(details[1], null, null, details[0]);
    },
    async expect => {
      browser.test.log(
        "Change global values, expect those changes reflected."
      );
      browser[action].setIcon({ path: "global.png" });
      browser[action].setPopup({ popup: "global.html" });
      browser[action].setTitle({ title: "Global Title" });
      browser[action].setBadgeText({ text: "g" });
      browser[action].setBadgeBackgroundColor({
        color: [0, 0xff, 0, 0xff],
      });
      browser[action].setBadgeTextColor({
        color: [0xff, 0, 0xff, 0xff],
      });
      browser[action].disable();

      expect(details[1], null, details[3], details[0]);
    },
    async expect => {
      browser.test.log("Re-enable globally. Expect enabled.");
      browser[action].enable();

      expect(details[1], null, details[4], details[0]);
    },
    async expect => {
      browser.test.log(
        "Switch back to tab 2. Expect former tab values, and new global values from previous steps."
      );
      await browser.tabs.update(tabs[1], { active: true });

      expect(details[2], null, details[4], details[0]);
    },
    async expect => {
      browser.test.log(
        "Navigate to a new page. Expect tab-specific values to be cleared."
      );

      let promise = promiseTabLoad({ id: tabs[1], url: "about:blank?1" });
      browser.tabs.update(tabs[1], { url: "about:blank?1" });
      await promise;

      expect(null, null, details[4], details[0]);
    },
    async expect => {
      browser.test.log(
        "Delete tab, switch back to tab 1. Expect previous results again."
      );
      await browser.tabs.remove(tabs[1]);
      expect(details[1], null, details[4], details[0]);
    },
    async expect => {
      browser.test.log("Create a new tab. Expect new global properties.");
      let tab = await browser.tabs.create({
        active: true,
        url: "about:blank?2",
      });
      tabs.push(tab.id);
      expect(null, null, details[4], details[0]);
    },
    async expect => {
      browser.test.log("Delete tab.");
      await browser.tabs.remove(tabs[2]);
      expect(details[1], null, details[4], details[0]);
    },
  ];
}'''

DEFAULT_TITLE_TESTS = r'''function (tabs) {
  let details = [
    {
      title: "Foo Extension",
      popup: "",
      badge: "",
      badgeBackgroundColor: [0xd9, 0, 0, 255],
      badgeTextColor: [0xff, 0xff, 0xff, 0xff],
      icon: browser.runtime.getURL("icon.png"),
      enabled: true,
    },
    { title: "Foo Title" },
    { title: "Bar Title" },
  ];

  return [
    async expect => {
      browser.test.log("Initial state. Expect default properties.");

      expect(null, null, null, details[0]);
    },
    async expect => {
      browser.test.log("Change the tab title. Expect new title.");
      browser.browserAction.setTitle({
        tabId: tabs[0],
        title: "Foo Title",
      });

      expect(details[1], null, null, details[0]);
    },
    async expect => {
      browser.test.log("Change the global title. Expect same properties.");
      browser.browserAction.setTitle({ title: "Bar Title" });

      expect(details[1], null, details[2], details[0]);
    },
    async expect => {
      browser.test.log("Clear the tab title. Expect new global title.");
      browser.browserAction.setTitle({ tabId: tabs[0], title: null });

      expect(null, null, details[2], details[0]);
    },
    async expect => {
      browser.test.log("Clear the global title. Expect default title.");
      browser.browserAction.setTitle({ title: null });

      expect(null, null, null, details[0]);
    },
    async expect => {
      browser.test.assertRejects(
        browser.browserAction.setPopup({ popup: "about:addons" }),
        /Access denied for URL about:addons/,
        "unable to set popup to about:addons"
      );

      expect(null, null, null, details[0]);
    },
  ];
}'''

PROPERTY_REMOVAL_TESTS = r'''function (tabs, windows) {
  let defaultIcon = "chrome://mozapps/skin/extensions/extensionGeneric.svg";
  let details = [
    {
      icon: browser.runtime.getURL("default.png"),
      popup: browser.runtime.getURL("default.html"),
      title: "Default Title",
      badge: "",
      badgeBackgroundColor: [0xd9, 0x00, 0x00, 0xff],
      badgeTextColor: [0xff, 0xff, 0xff, 0xff],
      enabled: true,
    },
    {
      icon: browser.runtime.getURL("global.png"),
      popup: browser.runtime.getURL("global.html"),
      title: "global",
      badge: "global",
      badgeBackgroundColor: [0x11, 0x11, 0x11, 0xff],
      badgeTextColor: [0x99, 0x99, 0x99, 0xff],
    },
    {
      icon: browser.runtime.getURL("window.png"),
      popup: browser.runtime.getURL("window.html"),
      title: "window",
      badge: "window",
      badgeBackgroundColor: [0x22, 0x22, 0x22, 0xff],
      badgeTextColor: [0x88, 0x88, 0x88, 0xff],
    },
    {
      icon: browser.runtime.getURL("tab.png"),
      popup: browser.runtime.getURL("tab.html"),
      title: "tab",
      badge: "tab",
      badgeBackgroundColor: [0x33, 0x33, 0x33, 0xff],
      badgeTextColor: [0x77, 0x77, 0x77, 0xff],
    },
    {
      icon: defaultIcon,
      popup: "",
      title: "",
      badge: "",
      badgeBackgroundColor: [0x33, 0x33, 0x33, 0xff],
      badgeTextColor: [0x77, 0x77, 0x77, 0xff],
    },
    {
      icon: browser.runtime.getURL("global2.png"),
      popup: browser.runtime.getURL("global2.html"),
      title: "global2",
      badge: "global2",
      badgeBackgroundColor: [0x44, 0x44, 0x44, 0xff],
      badgeTextColor: [0x66, 0x66, 0x66, 0xff],
    },
  ];

  return [
    async expect => {
      browser.test.log("Initial state, expect default properties.");
      expect(null, null, null, details[0]);
    },
    async expect => {
      browser.test.log("Set global values, expect the new values.");
      browser.browserAction.setIcon({ path: "global.png" });
      browser.browserAction.setPopup({ popup: "global.html" });
      browser.browserAction.setTitle({ title: "global" });
      browser.browserAction.setBadgeText({ text: "global" });
      browser.browserAction.setBadgeBackgroundColor({ color: "#111" });
      browser.browserAction.setBadgeTextColor({ color: "#999" });
      expect(null, null, details[1], details[0]);
    },
    async expect => {
      browser.test.log("Set window values, expect the new values.");
      let windowId = windows[0];
      browser.browserAction.setIcon({ windowId, path: "window.png" });
      browser.browserAction.setPopup({ windowId, popup: "window.html" });
      browser.browserAction.setTitle({ windowId, title: "window" });
      browser.browserAction.setBadgeText({ windowId, text: "window" });
      browser.browserAction.setBadgeBackgroundColor({
        windowId,
        color: "#222",
      });
      browser.browserAction.setBadgeTextColor({ windowId, color: "#888" });
      expect(null, details[2], details[1], details[0]);
    },
    async expect => {
      browser.test.log("Set tab values, expect the new values.");
      let tabId = tabs[0];
      browser.browserAction.setIcon({ tabId, path: "tab.png" });
      browser.browserAction.setPopup({ tabId, popup: "tab.html" });
      browser.browserAction.setTitle({ tabId, title: "tab" });
      browser.browserAction.setBadgeText({ tabId, text: "tab" });
      browser.browserAction.setBadgeBackgroundColor({
        tabId,
        color: "#333",
      });
      browser.browserAction.setBadgeTextColor({ tabId, color: "#777" });
      expect(details[3], details[2], details[1], details[0]);
    },
    async expect => {
      browser.test.log(
        "Set empty tab values, expect empty values except for colors."
      );
      let tabId = tabs[0];
      browser.browserAction.setIcon({ tabId, path: "" });
      browser.browserAction.setPopup({ tabId, popup: "" });
      browser.browserAction.setTitle({ tabId, title: "" });
      browser.browserAction.setBadgeText({ tabId, text: "" });
      await browser.test.assertRejects(
        browser.browserAction.setBadgeBackgroundColor({ tabId, color: "" }),
        /^Invalid badge background color: ""$/,
        "Expected invalid badge background color error"
      );
      await browser.test.assertRejects(
        browser.browserAction.setBadgeTextColor({ tabId, color: "" }),
        /^Invalid badge text color: ""$/,
        "Expected invalid badge text color error"
      );
      expect(details[4], details[2], details[1], details[0]);
    },
    async expect => {
      browser.test.log("Remove tab values, expect window values.");
      let tabId = tabs[0];
      browser.browserAction.setIcon({ tabId, path: null });
      browser.browserAction.setPopup({ tabId, popup: null });
      browser.browserAction.setTitle({ tabId, title: null });
      browser.browserAction.setBadgeText({ tabId, text: null });
      browser.browserAction.setBadgeBackgroundColor({ tabId, color: null });
      browser.browserAction.setBadgeTextColor({ tabId, color: null });
      expect(null, details[2], details[1], details[0]);
    },
    async expect => {
      browser.test.log("Remove window values, expect global values.");
      let windowId = windows[0];
      browser.browserAction.setIcon({ windowId, path: null });
      browser.browserAction.setPopup({ windowId, popup: null });
      browser.browserAction.setTitle({ windowId, title: null });
      browser.browserAction.setBadgeText({ windowId, text: null });
      browser.browserAction.setBadgeBackgroundColor({
        windowId,
        color: null,
      });
      browser.browserAction.setBadgeTextColor({ windowId, color: null });
      expect(null, null, details[1], details[0]);
    },
    async expect => {
      browser.test.log("Change global values, expect the new values.");
      browser.browserAction.setIcon({ path: "global2.png" });
      browser.browserAction.setPopup({ popup: "global2.html" });
      browser.browserAction.setTitle({ title: "global2" });
      browser.browserAction.setBadgeText({ text: "global2" });
      browser.browserAction.setBadgeBackgroundColor({ color: "#444" });
      browser.browserAction.setBadgeTextColor({ color: "#666" });
      expect(null, null, details[5], details[0]);
    },
    async expect => {
      browser.test.log("Remove global values, expect defaults.");
      browser.browserAction.setIcon({ path: null });
      browser.browserAction.setPopup({ popup: null });
      browser.browserAction.setBadgeText({ text: null });
      browser.browserAction.setTitle({ title: null });
      browser.browserAction.setBadgeBackgroundColor({ color: null });
      browser.browserAction.setBadgeTextColor({ color: null });
      expect(null, null, null, details[0]);
    },
  ];
}'''

MULTIPLE_WINDOWS_TESTS = r'''function (tabs, windows) {
  let details = [
    {
      icon: browser.runtime.getURL("default.png"),
      popup: browser.runtime.getURL("default.html"),
      title: "Default Title",
      badge: "",
      badgeBackgroundColor: [0xd9, 0x00, 0x00, 0xff],
      badgeTextColor: [0xff, 0xff, 0xff, 0xff],
      enabled: true,
    },
    {
      icon: browser.runtime.getURL("window1.png"),
      popup: browser.runtime.getURL("window1.html"),
      title: "window1",
      badge: "w1",
      badgeBackgroundColor: [0x11, 0x11, 0x11, 0xff],
      badgeTextColor: [0x99, 0x99, 0x99, 0xff],
    },
    {
      icon: browser.runtime.getURL("window2.png"),
      popup: browser.runtime.getURL("window2.html"),
      title: "window2",
      badge: "w2",
      badgeBackgroundColor: [0x22, 0x22, 0x22, 0xff],
      badgeTextColor: [0x88, 0x88, 0x88, 0xff],
    },
    { title: "tab" },
  ];

  return [
    async expect => {
      browser.test.log("Initial state, expect default properties.");
      expect(null, null, null, details[0]);
    },
    async expect => {
      browser.test.log("Set window values, expect the new values.");
      let windowId = windows[0];
      browser.browserAction.setIcon({ windowId, path: "window1.png" });
      browser.browserAction.setPopup({ windowId, popup: "window1.html" });
      browser.browserAction.setTitle({ windowId, title: "window1" });
      browser.browserAction.setBadgeText({ windowId, text: "w1" });
      browser.browserAction.setBadgeBackgroundColor({
        windowId,
        color: "#111",
      });
      browser.browserAction.setBadgeTextColor({ windowId, color: "#999" });
      expect(null, details[1], null, details[0]);
    },
    async expect => {
      browser.test.log("Create a new tab, expect window values.");
      let tab = await browser.tabs.create({ active: true });
      tabs.push(tab.id);
      expect(null, details[1], null, details[0]);
    },
    async expect => {
      browser.test.log("Set a tab title, expect it.");
      await browser.browserAction.setTitle({
        tabId: tabs[1],
        title: "tab",
      });
      expect(details[3], details[1], null, details[0]);
    },
    async expect => {
      browser.test.log("Open a new window, expect default values.");
      let { id } = await browser.windows.create();
      windows.push(id);
      expect(null, null, null, details[0]);
    },
    async expect => {
      browser.test.log("Set window values, expect the new values.");
      let windowId = windows[1];
      browser.browserAction.setIcon({ windowId, path: "window2.png" });
      browser.browserAction.setPopup({ windowId, popup: "window2.html" });
      browser.browserAction.setTitle({ windowId, title: "window2" });
      browser.browserAction.setBadgeText({ windowId, text: "w2" });
      browser.browserAction.setBadgeBackgroundColor({
        windowId,
        color: "#222",
      });
      browser.browserAction.setBadgeTextColor({ windowId, color: "#888" });
      expect(null, details[2], null, details[0]);
    },
    async expect => {
      browser.test.log(
        "Move tab from old window to the new one. Tab-specific data" +
          " is preserved but inheritance is from the new window"
      );
      await browser.tabs.move(tabs[1], { windowId: windows[1], index: -1 });
      await browser.tabs.update(tabs[1], { active: true });
      expect(details[3], details[2], null, details[0]);
    },
    async expect => {
      browser.test.log("Close the initial tab of the new window.");
      let [{ id }] = await browser.tabs.query({
        windowId: windows[1],
        index: 0,
      });
      await browser.tabs.remove(id);
      expect(details[3], details[2], null, details[0]);
    },
    async expect => {
      browser.test.log(
        "Move the previous tab to a 3rd window, the 2nd one will close."
      );
      await browser.windows.create({ tabId: tabs[1] });
      expect(details[3], null, null, details[0]);
    },
    async expect => {
      browser.test.log("Close the tab, go back to the 1st window.");
      await browser.tabs.remove(tabs[1]);
      expect(null, details[1], null, details[0]);
    },
    async expect => {
      browser.test.log(
        "Assert failures for bad parameters. Expect no change"
      );

      let calls = {
        setIcon: { path: "default.png" },
        setPopup: { popup: "default.html" },
        setTitle: { title: "Default Title" },
        setBadgeText: { text: "" },
        setBadgeBackgroundColor: { color: [0xd9, 0x00, 0x00, 0xff] },
        setBadgeTextColor: { color: [0xff, 0xff, 0xff, 0xff] },
        getPopup: {},
        getTitle: {},
        getBadgeText: {},
        getBadgeBackgroundColor: {},
      };
      for (let [method, arg] of Object.entries(calls)) {
        browser.test.assertThrows(
          () => browser.browserAction[method]({ ...arg, windowId: -3 }),
          /-3 is too small \(must be at least -2\)/,
          method + " with invalid windowId"
        );
        await browser.test.assertRejects(
          browser.browserAction[method]({
            ...arg,
            tabId: tabs[0],
            windowId: windows[0],
          }),
          /Only one of tabId and windowId can be specified/,
          method + " with both tabId and windowId"
        );
      }

      expect(null, details[1], null, details[0]);
    },
  ];
}'''

DEFAULT_BADGE_TEXT_COLOR_TESTS = r'''function (tabs, windows) {
  let details = [
    {
      icon: browser.runtime.getURL("default.png"),
      popup: browser.runtime.getURL("default.html"),
      title: "Default Title",
      badge: "",
      badgeBackgroundColor: [0xd9, 0x00, 0x00, 0xff],
      badgeTextColor: [0xff, 0xff, 0xff, 0xff],
      enabled: true,
    },
    {
      badgeBackgroundColor: [0xff, 0xff, 0x00, 0xff],
      badgeTextColor: [0x00, 0x00, 0x00, 0xff],
    },
    {
      badgeBackgroundColor: [0x00, 0x00, 0xff, 0xff],
      badgeTextColor: [0xff, 0xff, 0xff, 0xff],
    },
    {
      badgeBackgroundColor: [0xff, 0xff, 0xff, 0x00],
      badgeTextColor: [0x00, 0x00, 0x00, 0xff],
    },
    {
      badgeBackgroundColor: [0x00, 0x00, 0xff, 0xff],
      badgeTextColor: [0xff, 0x00, 0xff, 0xff],
    },
    { badgeBackgroundColor: [0xff, 0xff, 0xff, 0x00] },
    {
      badgeBackgroundColor: [0x00, 0x00, 0x00, 0x00],
      badgeTextColor: [0xff, 0xff, 0xff, 0xff],
    },
  ];

  return [
    async expect => {
      browser.test.log("Initial state, expect default properties.");
      expect(null, null, null, details[0]);
    },
    async expect => {
      browser.test.log("Set a global light bgcolor, expect black text.");
      browser.browserAction.setBadgeBackgroundColor({ color: "#ff0" });
      expect(null, null, details[1], details[0]);
    },
    async expect => {
      browser.test.log(
        "Set a window-specific dark bgcolor, expect white text."
      );
      let windowId = windows[0];
      browser.browserAction.setBadgeBackgroundColor({
        windowId,
        color: "#00f",
      });
      expect(null, details[2], details[1], details[0]);
    },
    async expect => {
      browser.test.log(
        "Set a tab-specific transparent-white bgcolor, expect black text."
      );
      let tabId = tabs[0];
      browser.browserAction.setBadgeBackgroundColor({
        tabId,
        color: "#fff0",
      });
      expect(details[3], details[2], details[1], details[0]);
    },
    async expect => {
      browser.test.log(
        "Set a window-specific text color, expect it in the tab."
      );
      let windowId = windows[0];
      browser.browserAction.setBadgeTextColor({ windowId, color: "#f0f" });
      expect(details[5], details[4], details[1], details[0]);
    },
    async expect => {
      browser.test.log(
        "Remove the window-specific text color, expect black again."
      );
      let windowId = windows[0];
      browser.browserAction.setBadgeTextColor({ windowId, color: null });
      expect(details[3], details[2], details[1], details[0]);
    },
    async expect => {
      browser.test.log(
        "Set a tab-specific transparent-black bgcolor, expect white text."
      );
      let tabId = tabs[0];
      browser.browserAction.setBadgeBackgroundColor({
        tabId,
        color: "#0000",
      });
      expect(details[6], details[2], details[1], details[0]);
    },
  ];
}'''


def image_files(*names):
    """The add-on's image files `names`."""
    return {name: png(IMAGES[name]) for name in names}


def serialize_color(color):
    """serializeColor() of the test: a colour as CSS writes it, here
    without its alpha."""
    if color is None:
        return None
    red, green, blue = color[:3]
    return f'rgb({red}, {green}, {blue})'


def icon_name(url):
    """The image file of an icon's URL; Firefox's generic icon is none."""
    if url.startswith('chrome-extension://'):
        return url.rsplit('/', 1)[1]
    return None


class BrowserActionContextTest(FirefoxTest):
    hosts = ('example.com',)
    routes = {'/': (200, {'Content-Type': 'text/html'},
                    b'<!DOCTYPE html><title>example.com</title><p>page')}

    def expected_state(self, details, title):
        """What the button shows for the getters' `details`, as
        head.action_button_state() reads it, with CSS colours."""
        badge = bool(details['badge'])
        state = {'title': title, 'icon': icon_name(details['icon']),
                 'enabled': details['enabled'], 'badge': badge,
                 'badge_background': None, 'badge_text_color': None}
        if badge:
            state['badge_background'] = serialize_color(details['badgeBackgroundColor'])
            state['badge_text_color'] = serialize_color(details['badgeTextColor'])
        return state

    def button_state(self, images, expected):
        """The button's state, once it is `expected`, or as it is after 5
        seconds, as Firefox waits for the icon, title and badge colours.
        `images` are the add-on's image files' colours."""
        found = {}

        def read():
            state = head.action_button_state(self, images)
            state['badge_background'] = serialize_color(state['badge_background'])
            state['badge_text_color'] = serialize_color(state['badge_text_color'])
            if not expected['badge']:
                state['badge_background'] = None
                state['badge_text_color'] = None
            found['state'] = state
            return state == expected
        try:
            wait_for(read, timeout=5, interval=0.2, what='the button')
        except AssertionError:
            pass
        return found['state']

    def check_widget_details(self, manifest, images, details):
        """checkWidgetDetails(): the button shows `details`."""
        title = details['title'] or manifest.get('name')
        expected = self.expected_state(details, title)
        state = self.button_state(images, expected)
        self.is_(state['icon'], expected['icon'], 'icon URL is correct')
        self.is_(state['title'], title, 'image title is correct')
        self.is_(state['title'], title, 'image label is correct')
        self.is_('a badge' if state['badge'] else 'no badge',
                 'a badge' if expected['badge'] else 'no badge', 'badge text is correct')
        self.is_(not state['enabled'], not details['enabled'], 'disabled state is correct')
        if details['badge']:
            for key, prop in (('badge_background', 'backgroundColor'),
                              ('badge_text_color', 'color')):
                self.is_(state[key], expected[key], f'Wait for expected badge {prop} to be set')

    def run_tests(self, manifest, files, get_tests):
        """runTests(): the add-on runs `get_tests`'s steps, and after each
        the button shows what its getters gave."""
        extension = self.load_extension(manifest=manifest, files=files,
                                        background=f'({BACKGROUND})({get_tests})')
        images = {name: IMAGES[name] for name in files if name in IMAGES}
        steps = []
        extension.on_message('nextTest', lambda *args: steps.append(args))
        extension.startup()
        while True:
            self.wait_reports(lambda: steps, 'the next test')
            expecting, _window_id, tests_remaining = steps.pop(0)
            self.check_widget_details(manifest, images, expecting)
            if not tests_remaining:
                break
            extension.send_message('runNextTest')
        extension.unload()

    def tab_switch_files(self):
        return {
            '_locales/en/messages.json': {
                'popup': {'message': 'default.html', 'description': 'Popup'},
                'title': {'message': 'Title', 'description': 'Title'},
            },
            **image_files('default.png', 'global.png', '1.png', '2.png'),
        }

    def test_01_tab_switch_context(self):
        self.run_tests({
            'browser_action': {
                'default_icon': 'default.png',
                'default_popup': '__MSG_popup__',
                'default_title': 'Default __MSG_title__',
                'default_area': 'navbar',
            },
            'default_locale': 'en',
            'permissions': ['tabs'],
        }, self.tab_switch_files(), TAB_SWITCH_TESTS)

    def test_02_tab_switch_action_context(self):
        self.run_tests({
            'manifest_version': 3,
            'action': {
                'default_icon': 'default.png',
                'default_popup': '__MSG_popup__',
                'default_title': 'Default __MSG_title__',
                'default_area': 'navbar',
            },
            'default_locale': 'en',
            'permissions': ['tabs'],
        }, self.tab_switch_files(), TAB_SWITCH_TESTS)

    def test_03_default_title(self):
        self.run_tests({
            'name': 'Foo Extension',
            'browser_action': {
                'default_icon': 'icon.png',
                'default_area': 'navbar',
            },
            'permissions': ['tabs'],
        }, image_files('icon.png'), DEFAULT_TITLE_TESTS)

    def test_04_badge_color_persistence(self):
        extension = self.load_extension(
            background=JS('''function () {
      browser.test.onMessage.addListener((msg, arg) => {
        browser.browserAction[msg](arg);
      });
    }'''),
            manifest={'browser_action': {'default_area': 'navbar'}})
        extension.startup()

        def badge_shown():
            """The badge, once its colour has changed."""
            def changed():
                state = head.action_button_state(self, {})
                return state if state['badge_background'] == (0, 255, 0) else None
            try:
                return wait_for(changed, timeout=5, interval=0.2, what='the badge colour')
            except AssertionError:
                return head.action_button_state(self, {})

        extension.send_message('setBadgeText', {'text': 'hi'})
        extension.send_message('setBadgeBackgroundColor', {'color': [0, 255, 0, 255]})

        state = badge_shown()
        self.is_(state['badge'], True, 'badge text is set in first window')
        self.is_(serialize_color(state['badge_background']), 'rgb(0, 255, 0)',
                 'badge color is set in first window')

        window_id = head.open_new_browser_window(self)

        state = badge_shown()
        self.is_(state['badge'], True, 'badge text is set in new window')
        self.is_(serialize_color(state['badge_background']), 'rgb(0, 255, 0)',
                 'badge color is set in new window')

        head.close_window(self, window_id)
        extension.unload()

    def test_05_property_removal(self):
        self.run_tests({
            'name': 'Generated extension',
            'browser_action': {
                'default_icon': 'default.png',
                'default_popup': 'default.html',
                'default_title': 'Default Title',
                'default_area': 'navbar',
            },
        }, image_files('default.png', 'global.png', 'global2.png', 'window.png', 'tab.png'),
            PROPERTY_REMOVAL_TESTS)

    def test_06_multiple_windows(self):
        self.run_tests({
            'browser_action': {
                'default_icon': 'default.png',
                'default_popup': 'default.html',
                'default_title': 'Default Title',
                'default_area': 'navbar',
            },
        }, image_files('default.png', 'window1.png', 'window2.png'), MULTIPLE_WINDOWS_TESTS)

    def test_07_default_badge_text_color(self):
        self.run_tests({
            'browser_action': {
                'default_icon': 'default.png',
                'default_popup': 'default.html',
                'default_title': 'Default Title',
                'default_area': 'navbar',
            },
        }, image_files('default.png', 'window1.png', 'window2.png'), DEFAULT_BADGE_TEXT_COLOR_TESTS)

    def test_08_navigation_clears_data(self):
        url = 'http://example.com/'
        default_title = 'Default title'
        tab_title = 'Tab title'
        tabs = []
        tab_ids = {}

        def add_tab(address, wait_for_load=True):
            page = self.open_tab(address) if wait_for_load else self.browser.new_tab(address)
            tabs.append(page)
            return page

        def send_message(method, param, expect=None, msg=None):
            message = {'method': method, 'param': param}
            if expect is not None:
                message['expect'] = expect
                message['msg'] = msg
            extension.send_message(message)
            extension.await_message('done')

        def expect_tab_specific_data(tab, msg):
            tab_id = tab_ids[tab.id]
            send_message('getBadgeText', {'tabId': tab_id}, 'foo', msg)
            send_message('getTitle', {'tabId': tab_id}, tab_title, msg)

        def expect_default_data(tab, msg):
            tab_id = tab_ids[tab.id]
            send_message('getBadgeText', {'tabId': tab_id}, '', msg)
            send_message('getTitle', {'tabId': tab_id}, default_title, msg)

        def set_tab_specific_data(tab):
            tab_id = tab_ids[tab.id]
            expect_default_data(tab, 'Expect default data before setting tab-specific data.')
            send_message('setBadgeText', {'tabId': tab_id, 'text': 'foo'})
            send_message('setTitle', {'tabId': tab_id, 'title': tab_title})
            expect_tab_specific_data(tab, 'Expect tab-specific data after setting it.')

        def navigate_tab(tab, address):
            """navigateTab(): the page goes to `address` itself, and the
            tab's location changes."""
            tab.eval(f'location.href = {json.dumps(address)}')
            wait_for(lambda: tab.eval('location.href') == address
                          and tab.eval('document.readyState') == 'complete',
                          what=f'{address} to load')

        def history_push_state(tab, address):
            tab.eval(f'history.pushState(null, null, {json.dumps(address)})')
            wait_for(lambda: tab.eval('location.href') == address, what=f'{address}')

        # Load a tab before installing the extension.
        tab1 = add_tab(url)

        extension = self.load_extension(
            manifest={'browser_action': {'default_title': default_title}},
            background=JS('''function () {
      browser.test.onMessage.addListener(
        async ({ method, param, expect, msg }) => {
          let result = await browser.browserAction[method](param);
          if (expect !== undefined) {
            browser.test.assertEq(expect, result, msg);
          }
          browser.test.sendMessage("done");
        }
      );
    }'''))
        extension.startup()
        tab_ids[tab1.id] = head.active_tab_id(self, extension)

        # Set tab-specific data to the existing tab.
        set_tab_specific_data(tab1)

        # Add a hash. Does not cause navigation.
        navigate_tab(tab1, url + '#hash')
        expect_tab_specific_data(tab1, 'Adding a hash does not clear tab-specific data')

        # Remove the hash. Causes navigation.
        navigate_tab(tab1, url)
        expect_default_data(tab1, 'Removing hash clears tab-specific data')

        # Open a new tab, set tab-specific data to it.
        tab2 = add_tab('chrome://newtab/', wait_for_load=False)
        tab_ids[tab2.id] = head.active_tab_id(self, extension)
        set_tab_specific_data(tab2)

        # Load a page in that tab.
        navigate_tab(tab2, url)
        expect_default_data(tab2, 'Loading a page clears tab-specific data.')

        # Set tab-specific data.
        set_tab_specific_data(tab2)

        # Push history state. Does not cause navigation.
        history_push_state(tab2, url + '/path')
        expect_tab_specific_data(tab2, 'history.pushState() does not clear tab-specific data')

        # Navigate when the tab is not selected.
        self.browser.browser_call('Target.activateTarget', targetId=tab1.id)
        navigate_tab(tab2, url)
        expect_default_data(tab2, 'Navigating clears tab-specific data, even when not selected.')

        for tab in tabs:
            self.browser.close_target(tab)
        extension.unload()
