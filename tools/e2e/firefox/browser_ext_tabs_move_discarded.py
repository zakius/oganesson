"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_tabs_move_discarded.js.

The add-ons' code is Firefox's, as it is. Their tabs at https://example.com/
stay discarded, so they load nothing and need no server."""

from extension_test_utils import JS, FirefoxTest


class TabsMoveDiscardedTest(FirefoxTest):

    def test_01_move_discarded_to_window(self):
        extension = self.load_extension(
            manifest={'permissions': ['tabs']},
            background=JS('''async function() {
      // Create a discarded tab
      let url = "https://example.com/";
      let tab = await browser.tabs.create({ url, discarded: true });
      browser.test.assertEq(true, tab.discarded, "Tab should be discarded");
      browser.test.assertEq(url, tab.url, "Tab URL should be correct");

      // Create a new window
      let { id: windowId } = await browser.windows.create();

      // Move the tab into that window
      [tab] = await browser.tabs.move(tab.id, { windowId, index: -1 });
      browser.test.assertTrue(tab.discarded, "Tab should still be discarded");
      browser.test.assertEq(url, tab.url, "Tab URL should still be correct");

      await browser.windows.remove(windowId);
      browser.test.notifyPass("tabs.move");
    }'''))

        extension.startup()
        extension.await_finish('tabs.move')
        extension.unload()

    def test_02_move_hidden_discarded_to_window(self):
        extension_without_tabs_permission = self.load_extension(
            manifest={
                'permissions': ['https://example.com/'],
            },
            background=JS('''function() {
      browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
        if (changeInfo.hidden) {
          browser.test.assertEq(
            tab.url,
            "https://example.com/?hideme",
            "tab.url is correctly observed without tabs permission"
          );
          browser.test.sendMessage("onUpdated_checked");
        }
      });
      // Listener with "urls" filter, regression test for
      // https://bugzilla.mozilla.org/show_bug.cgi?id=1695346
      browser.tabs.onUpdated.addListener(
        (tabId, changeInfo) => {
          browser.test.assertTrue(changeInfo.hidden, "tab was hidden");
          browser.test.sendMessage("onUpdated_urls_filter");
        },
        {
          properties: ["hidden"],
          urls: ["https://example.com/?hideme"],
        }
      );
    }'''))
        extension_without_tabs_permission.startup()

        extension = self.load_extension(
            manifest={'permissions': ['tabs', 'tabHide']},
            # ExtensionControlledPopup's populateDescription method requires an addon:
            use_addon_manager='temporary',
            background=JS('''async function() {
      let url = "https://example.com/?hideme";
      let tab = await browser.tabs.create({ url, discarded: true });
      await browser.tabs.hide(tab.id);

      let { id: windowId } = await browser.windows.create();

      // Move the tab into that window
      [tab] = await browser.tabs.move(tab.id, { windowId, index: -1 });
      browser.test.assertTrue(tab.discarded, "Tab should still be discarded");
      browser.test.assertTrue(tab.hidden, "Tab should still be hidden");
      browser.test.assertEq(url, tab.url, "Tab URL should still be correct");

      await browser.windows.remove(windowId);
      browser.test.notifyPass("move_hidden_discarded_to_window");
    }'''))

        extension.startup()
        extension.await_finish('move_hidden_discarded_to_window')
        extension.unload()

        extension_without_tabs_permission.await_message('onUpdated_checked')
        extension_without_tabs_permission.await_message('onUpdated_urls_filter')
        extension_without_tabs_permission.unload()
