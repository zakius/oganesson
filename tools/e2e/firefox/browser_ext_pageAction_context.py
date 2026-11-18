"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_context.js.

The add-ons' code is Firefox's, but for the URL of Firefox's new tab page,
about:newtab: a new tab here opens chrome://newtab/, which loads
chrome://new-tab-page/, the URL that webNavigation gives. runTests() is
head_pageAction.py's, whose checks of the page action's button in the
location bar wait for that button (zakius/oganesson#68). example.com is a
local server here.

Left out of test_02_multiple_windows: the pref that stops Firefox preloading
its new tab page (browser.newtab.preload), a Gecko internal.
test_03_navigation_clears_data reads the tabs' IDs (Firefox's tabTracker) in
the add-on's background through DevTools (head.active_tab_id()), and
navigateTab() is load_url(): the browser loads the URL in the tab.
"""

from firefox import head, head_pageAction
from extension_test_utils import JS, FirefoxTest

HTML = {'Content-Type': 'text/html'}

GET_TESTS_TAB_SWITCH_CONTEXT = r'''
function (tabs) {
  let defaultIcon = "chrome://mozapps/skin/extensions/extensionGeneric.svg";
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
    { icon: defaultIcon, popup: "", title: "" },
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
      browser.test.log(
        "Set empty string values. Expect empty strings but default icon."
      );
      browser.pageAction.setIcon({ tabId: tabs[1], path: "" });
      browser.pageAction.setPopup({ tabId: tabs[1], popup: "" });
      browser.pageAction.setTitle({ tabId: tabs[1], title: "" });

      expect(details[3]);
    },
    expect => {
      browser.test.log("Clear the values. Expect default ones.");
      browser.pageAction.setIcon({ tabId: tabs[1], path: null });
      browser.pageAction.setPopup({ tabId: tabs[1], popup: null });
      browser.pageAction.setTitle({ tabId: tabs[1], title: null });

      expect(details[0]);
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
    async expect => {
      browser.test.assertRejects(
        browser.pageAction.setPopup({
          tabId: tabs[0],
          popup: "about:addons",
        }),
        /Access denied for URL about:addons/,
        "unable to set popup to about:addons"
      );

      expect(null);
    },
  ];
}'''

GET_TESTS_MULTIPLE_WINDOWS = r'''
function (tabs, windows) {
  let details = [
    {
      icon: browser.runtime.getURL("default.png"),
      popup: browser.runtime.getURL("default.html"),
      title: "Default Title",
    },
    {
      icon: browser.runtime.getURL("tab.png"),
      popup: browser.runtime.getURL("tab.html"),
      title: "tab",
    },
  ];

  function promiseWebNavigationCompleted(url) {
    return new Promise(resolve => {
      // The pageAction visibility state is reset when the location changes.
      // The webNavigation.onCompleted event is triggered when that happens.
      browser.webNavigation.onCompleted.addListener(
        function listener() {
          browser.webNavigation.onCompleted.removeListener(listener);
          resolve();
        },
        {
          url: [{ urlEquals: url }],
        }
      );
    });
  }

  return [
    async expect => {
      browser.test.log("Create a new tab, expect hidden pageAction.");
      let promise = promiseWebNavigationCompleted("chrome://new-tab-page/");
      let tab = await browser.tabs.create({ active: true });
      await promise;
      tabs.push(tab.id);
      expect(null);
    },
    async expect => {
      browser.test.log("Show the pageAction, expect default values.");
      await browser.pageAction.show(tabs[1]);
      expect(details[0]);
    },
    async expect => {
      browser.test.log("Set tab-specific values, expect them.");
      await browser.pageAction.setIcon({ tabId: tabs[1], path: "tab.png" });
      await browser.pageAction.setPopup({
        tabId: tabs[1],
        popup: "tab.html",
      });
      await browser.pageAction.setTitle({ tabId: tabs[1], title: "tab" });
      expect(details[1]);
    },
    async expect => {
      browser.test.log("Open a new window, expect hidden pageAction.");
      let { id } = await browser.windows.create();
      windows.push(id);
      expect(null);
    },
    async expect => {
      browser.test.log(
        "Move tab from old window to the new one, expect old values."
      );
      await browser.tabs.move(tabs[1], { windowId: windows[1], index: -1 });
      await browser.tabs.update(tabs[1], { active: true });
      expect(details[1]);
    },
    async expect => {
      browser.test.log("Close the initial tab of the new window.");
      let [{ id }] = await browser.tabs.query({
        windowId: windows[1],
        index: 0,
      });
      await browser.tabs.remove(id);
      expect(details[1]);
    },
    async expect => {
      browser.test.log(
        "Move the previous tab to a 3rd window, the 2nd one will close."
      );
      await browser.windows.create({ tabId: tabs[1] });
      expect(details[1]);
    },
    async expect => {
      browser.test.log("Close the tab, go back to the 1st window.");
      await browser.tabs.remove(tabs[1]);
      expect(null);
    },
  ];
}'''


class PageActionContextTest(FirefoxTest):
    hosts = ('example.com',)
    routes = {'/': (200, HTML, b'<!DOCTYPE html><title>example.com</title><p>page')}

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

    def test_02_multiple_windows(self):
        head_pageAction.run_tests(
            self,
            manifest={
                'page_action': {
                    'default_icon': 'default.png',
                    'default_popup': 'default.html',
                    'default_title': 'Default Title',
                },
                'permissions': ['webNavigation'],
            },
            files={
                'default.png': head.IMAGE_BUFFER,
                'tab.png': head.IMAGE_BUFFER,
            },
            get_tests=GET_TESTS_MULTIPLE_WINDOWS)

    def test_03_navigation_clears_data(self):
        url = 'http://example.com/'
        default_title = 'Default title'
        tab_title = 'Tab title'

        tabs = []

        def add_tab(url, wait_for_load):
            # BrowserTestUtils.openNewForegroundTab().
            if wait_for_load:
                tab = self.open_tab(url)
            else:
                tab = self.browser.new_tab(url)
            tabs.append(tab)
            return tab

        def send_message(method, param, expect=None, msg=None):
            # Firefox's message has no `expect` when the call's result isn't
            # checked.
            message = {'method': method, 'param': param, 'msg': msg}
            if expect is not None:
                message['expect'] = expect
            extension.send_message(message)
            extension.await_message('done')

        def expect_tab_specific_data(tab_id, msg):
            send_message('isShown', {'tabId': tab_id}, True, msg)
            send_message('getTitle', {'tabId': tab_id}, tab_title, msg)

        def expect_default_data(tab_id, msg):
            send_message('isShown', {'tabId': tab_id}, False, msg)
            send_message('getTitle', {'tabId': tab_id}, default_title, msg)

        def set_tab_specific_data(tab_id):
            expect_default_data(tab_id, 'Expect default data before setting tab-specific data.')
            send_message('show', tab_id)
            send_message('setTitle', {'tabId': tab_id, 'title': tab_title})
            expect_tab_specific_data(tab_id, 'Expect tab-specific data after setting it.')

        # Load a tab before installing the extension
        tab1 = add_tab(url, True)

        extension = self.load_extension(
            manifest={
                'page_action': {'default_title': default_title},
            },
            background=JS('''function () {
      browser.test.onMessage.addListener(
        async ({ method, param, expect, msg }) => {
          let result = await browser.pageAction[method](param);
          if (expect !== undefined) {
            browser.test.assertEq(expect, result, msg);
          }
          browser.test.sendMessage("done");
        }
      );
    }'''))
        extension.startup()
        tab1_id = head.active_tab_id(self, extension)

        # Set tab-specific data to the existing tab.
        set_tab_specific_data(tab1_id)

        # Add a hash. Does not cause navigation.
        self.load_url(tab1, url + '#hash')
        expect_tab_specific_data(tab1_id, 'Adding a hash does not clear tab-specific data')

        # Remove the hash. Causes navigation.
        self.load_url(tab1, url)
        expect_default_data(tab1_id, 'Removing hash clears tab-specific data')

        # Open a new tab, set tab-specific data to it.
        tab2 = add_tab('chrome://newtab/', False)
        tab2_id = head.active_tab_id(self, extension)
        set_tab_specific_data(tab2_id)

        # Load a page in that tab.
        self.load_url(tab2, url)
        expect_default_data(tab2_id, 'Loading a page clears tab-specific data.')

        # Set tab-specific data.
        set_tab_specific_data(tab2_id)

        # Push history state. Does not cause navigation.
        head.history_push_state(tab2, url + '/path')
        expect_tab_specific_data(tab2_id, 'history.pushState() does not clear tab-specific data')

        # Navigate when the tab is not selected
        self.browser.browser_call('Target.activateTarget', targetId=tab1.id)
        self.load_url(tab2, url)
        expect_default_data(tab2_id, 'Navigating clears tab-specific data, even when not selected.')

        for tab in tabs:
            self.browser.close_target(tab)
        extension.unload()
