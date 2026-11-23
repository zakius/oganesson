"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_activeTab.js.

The add-ons' code is Firefox's, as it is. https://example.com/ is a local
HTTPS server here. clickPageAction() with {button: 1} is a real middle click
on the page action's button in the location bar
(head.wait_page_action_button()). Firefox's
ext.tabManager.hasActiveTabPermission(tab), a Gecko internal, is read here
from what the grant gives: the selected tab's URL in the tabs API, which the
add-on, without the "tabs" permission or a host permission, gets only with
activeTab granted for it (has_active_tab_permission()).
"""

import tempfile
from pathlib import Path

from extension_test_utils import JS, FirefoxTest
from firefox import head
from harness import Server
from test_browser_traffic import certificate

HTML = {'Content-Type': 'text/html'}
ROUTES = {'/': (200, HTML, b'<!DOCTYPE html><title>example.com</title><p>example.com')}


def has_active_tab_permission(test, extension):
    """ext.tabManager.hasActiveTabPermission() of the selected tab: the
    add-on's background reads the tab's URL, which Chromium's tabs API gives
    it only where activeTab is granted."""
    page = test.browser.extension_background(extension.id)
    try:
        return page.eval('chrome.tabs.query({active: true, lastFocusedWindow: true})'
                         '.then(tabs => tabs[0].url !== undefined)', gesture=False)
    finally:
        page.close()


def middle_click_page_action(test, extension):
    """clickPageAction(extension, window, {button: 1})."""
    head.synthesize_mouse_at_center(test, head.wait_page_action_button(test, extension), button=1)


class PageActionActiveTabTest(FirefoxTest):

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-pageaction-activetab-'))
        cls.https = Server(ROUTES, tls=certificate(cls.folder, 'example.com'))
        cls.host_rules = (f'MAP example.com 127.0.0.1:{cls.https.port}',)
        cls.browser_args = (*cls.browser_args, '--ignore-certificate-errors')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.https.stop()

    def test_01_middle_click_with_activeTab(self):
        tab = self.open_tab('https://example.com/')
        self.addCleanup(self.browser.close_target, tab)

        extension = self.load_extension(
            manifest={
                'page_action': {},
                'permissions': ['activeTab'],
            },

            background=JS('''async function background() {
      browser.pageAction.onClicked.addListener(async (tab, info) => {
        browser.test.assertEq(1, info.button, "Expected button value");
        browser.test.assertEq(
          "https://example.com/",
          tab.url,
          "tab.url has the expected url"
        );
        await browser.tabs.insertCSS(tab.id, {
          code: "body { border: 20px solid red; }",
        });
        browser.test.sendMessage("onClick");
      });

      let [tab] = await browser.tabs.query({
        active: true,
        currentWindow: true,
      });
      await browser.pageAction.show(tab.id);
      browser.test.sendMessage("ready");
    }'''))

        extension.startup()
        extension.await_message('ready')

        self.is_(has_active_tab_permission(self, extension), False,
                 'Active tab was not granted permission')

        middle_click_page_action(self, extension)
        extension.await_message('onClick')

        self.is_(has_active_tab_permission(self, extension), True,
                 'Active tab was granted permission')
        extension.unload()

    def test_02_middle_click_without_activeTab(self):
        tab = self.open_tab('https://example.com/')
        self.addCleanup(self.browser.close_target, tab)

        extension = self.load_extension(
            manifest={
                'page_action': {},
            },

            background=JS('''async function background() {
      browser.pageAction.onClicked.addListener(async (tab, info) => {
        browser.test.assertEq(1, info.button, "Expected button value");
        browser.test.assertEq(tab.url, undefined, "tab.url is undefined");
        await browser.test.assertRejects(
          browser.tabs.insertCSS(tab.id, {
            code: "body { border: 20px solid red; }",
          }),
          "Missing host permission for the tab",
          "expected failure of tabs.insertCSS without permission"
        );
        browser.test.sendMessage("onClick");
      });

      let [tab] = await browser.tabs.query({
        active: true,
        currentWindow: true,
      });
      await browser.pageAction.show(tab.id);
      browser.test.sendMessage("ready");
    }'''))

        extension.startup()
        extension.await_message('ready')

        middle_click_page_action(self, extension)
        extension.await_message('onClick')

        extension.unload()
