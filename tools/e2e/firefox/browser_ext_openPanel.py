"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_openPanel.js.

The add-on's code is Firefox's, as it is. `BrowserTestUtils.synthesizeMouseAtCenter()`
on the add-on's tab.html is a real click on the button in the tab
(harness.Browser.click_element()), so that the add-on's call runs from a user
input handler. closePageAction() closes the popup's page, and waits for its
bubble, Chromium's ExtensionPopup, to go (head_pageAction.wait_popup_hidden()).
Firefox's sidebar is the side panel, where an add-on's `sidebar_action` page
is to show (zakius/oganesson#86): SidebarController.isOpen is a side panel
(SidePanel) that shows.

Firefox loads the add-on with `startupReason: "APP_STARTUP"`, so that its
sidebar doesn't open at install; the harness has no startup reason, and loads
the add-on as an install: not needed, as this browser's side panel doesn't
open when an add-on installs.

The add-on's sidebarAction checks need sidebarAction (zakius/oganesson#86):
until then its background throws at `browser.sidebarAction`, and its "ready"
never comes.
"""

from firefox import head, head_pageAction
from extension_test_utils import JS, FirefoxTest
from harness import Page, wait_for


def sidebar_is_open(test):
    """SidebarController.isOpen: the side panel shows."""
    return any(view.visible for view in test.browser.views('SidePanel'))


def close_page_action(test, extension):
    """closePageAction(): the add-on's popup closes."""
    for target in head_pageAction.popup_targets(test, extension):
        test.browser.close_target(Page(target))
    head_pageAction.wait_popup_hidden(test, extension)


class OpenPanelTest(FirefoxTest):

    def test_01_openPopup_requires_user_interaction(self):
        background_script = JS('''async function backgroundScript() {
    browser.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
      if (changeInfo.status != "complete") {
        return;
      }
      await browser.pageAction.show(tabId);

      await browser.test.assertRejects(
        browser.pageAction.openPopup(),
        "pageAction.openPopup may only be called from a user input handler",
        "The error is informative."
      );
      await browser.test.assertRejects(
        browser.sidebarAction.open(),
        "sidebarAction.open may only be called from a user input handler",
        "The error is informative."
      );
      await browser.test.assertRejects(
        browser.sidebarAction.close(),
        "sidebarAction.close may only be called from a user input handler",
        "The error is informative."
      );
      await browser.test.assertRejects(
        browser.sidebarAction.toggle(),
        "sidebarAction.toggle may only be called from a user input handler",
        "The error is informative."
      );

      browser.runtime.onMessage.addListener(async msg => {
        browser.test.assertEq(msg, "from-panel", "correct message received");
        browser.test.sendMessage("panel-opened");
      });

      browser.test.sendMessage("ready");
    });
    browser.tabs.create({ url: "tab.html" });
  }''')

        extension = self.load_extension(
            background=background_script,
            manifest={
                'browser_action': {
                    'default_popup': 'panel.html',
                },
                'page_action': {
                    'default_popup': 'panel.html',
                },
                'sidebar_action': {
                    'default_panel': 'panel.html',
                },
            },

            files={
                'tab.html': '''
      <!DOCTYPE html>
      <html><head><meta charset="utf-8"></head><body>
      <button id="openPageAction">openPageAction</button>
      <button id="openSidebarAction">openSidebarAction</button>
      <button id="closeSidebarAction">closeSidebarAction</button>
      <button id="toggleSidebarAction">toggleSidebarAction</button>
      <script src="tab.js"></script>
      </body></html>
      ''',
                'panel.html': '''
      <!DOCTYPE html>
      <html><head><meta charset="utf-8"></head><body>
      <script src="panel.js"></script>
      </body></html>
      ''',
                'tab.js': JS('''function () {
        document.getElementById("openPageAction").addEventListener(
          "click",
          () => {
            browser.pageAction.openPopup();
          },
          { once: true }
        );
        document.getElementById("openSidebarAction").addEventListener(
          "click",
          () => {
            browser.sidebarAction.open();
          },
          { once: true }
        );
        document.getElementById("closeSidebarAction").addEventListener(
          "click",
          () => {
            browser.sidebarAction.close();
          },
          { once: true }
        );
        /* eslint-disable mozilla/balanced-listeners */
        document
          .getElementById("toggleSidebarAction")
          .addEventListener("click", () => {
            browser.sidebarAction.toggle();
          });
        /* eslint-enable mozilla/balanced-listeners */
      }'''),
                'panel.js': JS('''function () {
        browser.runtime.sendMessage("from-panel");
        browser.test.onMessage.addListener(async msg => {
          browser.test.assertEq("window_close", msg, "Expected msg");
          window.close();
        });
      }'''),
            })

        def click(id):
            self.browser.click_element(tab, id)
            return extension.await_message('panel-opened')

        extension.startup()
        extension.await_message('ready')
        tab = head.extension_tab(self, extension, 'tab.html')

        click('#openPageAction')
        close_page_action(self, extension)

        click('#openSidebarAction')

        self.browser.click_element(tab, '#closeSidebarAction')
        wait_for(lambda: not sidebar_is_open(self), what='the sidebar to close')

        click('#toggleSidebarAction')
        wait_for(lambda: sidebar_is_open(self), what='the sidebar to open')
        self.browser.click_element(tab, '#toggleSidebarAction')
        wait_for(lambda: not sidebar_is_open(self), what='the sidebar to close')

        click('#toggleSidebarAction')
        wait_for(lambda: sidebar_is_open(self), what='the sidebar to open')

        extension.send_message('window_close')
        wait_for(lambda: not sidebar_is_open(self), what='the sidebar to close')

        self.browser.close_target(tab)
        extension.unload()
