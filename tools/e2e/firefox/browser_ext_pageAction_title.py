"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_title.js.

The add-ons' code is Firefox's, as it is. runTests() is head_pageAction.py's,
whose checks of the page action's button in the location bar wait for that
button.
"""

from firefox import head, head_pageAction
from extension_test_utils import FirefoxTest

GET_TESTS_TAB_SWITCH_CONTEXT = r'''
function (tabs) {
  let details = [
    {
      icon: browser.runtime.getURL("default.png"),
      popup: browser.runtime.getURL("default.html"),
      title: "Default T\u00edtulo \u263a",
    },
    {
      icon: browser.runtime.getURL("1.png"),
      popup: browser.runtime.getURL("default.html"),
      title: "Default T\u00edtulo \u263a",
    },
    {
      icon: browser.runtime.getURL("2.png"),
      popup: browser.runtime.getURL("2.html"),
      title: "Title 2",
    },
    {
      icon: browser.runtime.getURL("2.png"),
      popup: browser.runtime.getURL("2.html"),
      title: "",
    },
    {
      icon: browser.runtime.getURL("2.png"),
      popup: browser.runtime.getURL("2.html"),
      title: "Default T\u00edtulo \u263a",
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
    expect => {
      browser.test.log("Initial state. No icon visible.");
      expect(null);
    },
    async expect => {
      browser.test.log(
        "Show the icon on the first tab, expect default properties."
      );
      await browser.pageAction.show(tabs[0]);
      expect(details[0]);
    },
    expect => {
      browser.test.log(
        "Change the icon. Expect default properties excluding the icon."
      );
      browser.pageAction.setIcon({ tabId: tabs[0], path: "1.png" });
      expect(details[1]);
    },
    async expect => {
      browser.test.log("Create a new tab. No icon visible.");
      let tab = await browser.tabs.create({
        active: true,
        url: "about:blank?0",
      });
      tabs.push(tab.id);
      expect(null);
    },
    async expect => {
      browser.test.log("Await tab load. No icon visible.");
      let promise = promiseTabLoad({ id: tabs[1], url: "about:blank?0" });
      let { url } = await browser.tabs.get(tabs[1]);
      if (url === "about:blank") {
        await promise;
      }
      expect(null);
    },
    async expect => {
      browser.test.log("Change properties. Expect new properties.");
      let tabId = tabs[1];

      await browser.pageAction.show(tabId);
      browser.pageAction.setIcon({ tabId, path: "2.png" });
      browser.pageAction.setPopup({ tabId, popup: "2.html" });
      browser.pageAction.setTitle({ tabId, title: "Title 2" });

      expect(details[2]);
    },
    async expect => {
      browser.test.log("Change the hash. Expect same properties.");

      let promise = promiseTabLoad({
        id: tabs[1],
        url: "about:blank?0#ref",
      });

      browser.tabs.update(tabs[1], { url: "about:blank?0#ref" });

      await promise;
      expect(details[2]);
    },
    expect => {
      browser.test.log("Set empty title. Expect empty title.");
      browser.pageAction.setTitle({ tabId: tabs[1], title: "" });

      expect(details[3]);
    },
    expect => {
      browser.test.log("Clear the title. Expect default title.");
      browser.pageAction.setTitle({ tabId: tabs[1], title: null });

      expect(details[4]);
    },
    async expect => {
      browser.test.log("Navigate to a new page. Expect icon hidden.");

      // TODO: This listener should not be necessary, but the |tabs.update|
      // callback currently fires too early in e10s windows.
      let promise = promiseTabLoad({ id: tabs[1], url: "about:blank?1" });

      browser.tabs.update(tabs[1], { url: "about:blank?1" });

      await promise;
      expect(null);
    },
    async expect => {
      browser.test.log("Show the icon. Expect default properties again.");
      await browser.pageAction.show(tabs[1]);
      expect(details[0]);
    },
    async expect => {
      browser.test.log(
        "Switch back to the first tab. Expect previously set properties."
      );
      await browser.tabs.update(tabs[0], { active: true });
      expect(details[1]);
    },
    async expect => {
      browser.test.log(
        "Hide the icon on tab 2. Switch back, expect hidden."
      );
      await browser.pageAction.hide(tabs[1]);
      await browser.tabs.update(tabs[1], { active: true });
      expect(null);
    },
    async expect => {
      browser.test.log(
        "Switch back to tab 1. Expect previous results again."
      );
      await browser.tabs.remove(tabs[1]);
      expect(details[1]);
    },
    async expect => {
      browser.test.log("Hide the icon. Expect hidden.");
      await browser.pageAction.hide(tabs[0]);
      expect(null);
    },
  ];
}'''

GET_TESTS_DEFAULT_TITLE = r'''
function (tabs) {
  let details = [
    {
      title: "Foo Extension",
      popup: "",
      icon: browser.runtime.getURL("icon.png"),
    },
    {
      title: "Foo Title",
      popup: "",
      icon: browser.runtime.getURL("icon.png"),
    },
    { title: "", popup: "", icon: browser.runtime.getURL("icon.png") },
  ];

  return [
    expect => {
      browser.test.log("Initial state. No icon visible.");
      expect(null);
    },
    async expect => {
      browser.test.log(
        "Show the icon on the first tab, expect extension title as default title."
      );
      await browser.pageAction.show(tabs[0]);
      expect(details[0]);
    },
    expect => {
      browser.test.log("Change the title. Expect new title.");
      browser.pageAction.setTitle({ tabId: tabs[0], title: "Foo Title" });
      expect(details[1]);
    },
    expect => {
      browser.test.log("Set empty title. Expect empty title.");
      browser.pageAction.setTitle({ tabId: tabs[0], title: "" });
      expect(details[2]);
    },
    expect => {
      browser.test.log("Clear the title. Expect extension title.");
      browser.pageAction.setTitle({ tabId: tabs[0], title: null });
      expect(details[0]);
    },
  ];
}'''


class PageActionTitleTest(FirefoxTest):

    def test_01_tab_switch_context(self):
        head_pageAction.run_tests(
            self,
            manifest={
                'name': 'Foo Extension',

                'page_action': {
                    'default_icon': 'default.png',
                    'default_popup': '__MSG_popup__',
                    'default_title': 'Default __MSG_title__ ☺',
                },

                'default_locale': 'en',

                'permissions': ['tabs'],
            },
            files={
                '_locales/en/messages.json': {
                    'popup': {
                        'message': 'default.html',
                        'description': 'Popup',
                    },

                    'title': {
                        'message': 'Title',
                        'description': 'Title',
                    },
                },

                '_locales/es_ES/messages.json': {
                    'popup': {
                        'message': 'default.html',
                        'description': 'Popup',
                    },

                    'title': {
                        'message': 'Título',
                        'description': 'Title',
                    },
                },

                'default.png': head.IMAGE_BUFFER,
                '1.png': head.IMAGE_BUFFER,
                '2.png': head.IMAGE_BUFFER,
            },
            get_tests=GET_TESTS_TAB_SWITCH_CONTEXT)

    def test_02_default_title(self):
        head_pageAction.run_tests(
            self,
            manifest={
                'name': 'Foo Extension',

                'page_action': {
                    'default_icon': 'icon.png',
                },

                'permissions': ['tabs'],
            },
            files={
                'icon.png': head.IMAGE_BUFFER,
            },
            get_tests=GET_TESTS_DEFAULT_TITLE)
