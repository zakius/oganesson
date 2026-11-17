"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_activeTab.js.

Firefox's test moves its two tabs to the start of the tab strip
(gBrowser.moveTabTo()); the port closes the window's other tabs after it
opens the first, so the two are the strip's first and second, and opens a
blank tab before it closes them, so that the window stays. Left out:
focusing the selected tab so that Firefox's tab strip loads its
localization, a Gecko internal.
"""

from firefox import head
from extension_test_utils import JS

PAGE_URL = f'{head.BASE}context.html'
OTHER_URL = f'http://127.0.0.1:8888{head.DIR}context.html'


class MenusActiveTabTest(head.ContextMenuTest):
    hosts = ('mochi.test', '127.0.0.1')

    def open_two_tabs_and_open_tab_menu(self, on_tab_menu_clicked):
        """openTwoTabsAndOpenTabMenu(): two tabs at the start of the tab
        strip, the second selected; the add-on's `tab` item, clicked in the
        first tab's context menu, runs `on_tab_menu_clicked` (JavaScript)."""
        tab1 = self.open_tab(PAGE_URL)
        for target in self.browser.targets():
            if target['type'] == 'page' and target['id'] != tab1.id:
                self.browser.browser_call('Target.closeTarget', targetId=target['id'])
        tab2 = self.open_tab(OTHER_URL)

        background = JS('''async function background(onTabMenuClicked) {
          browser.menus.onClicked.addListener(async (info, tab) => {
            await onTabMenuClicked(info, tab);
            browser.test.sendMessage("onCommand_on_tab_click");
          });

          browser.menus.create(
            {
              title: "menu item on tab",
              contexts: ["tab"],
            },
            () => {
              browser.test.sendMessage("ready");
            }
          );
        }''', on_tab_menu_clicked)
        extension = self.load_extension(
            manifest={
                'permissions': ['menus', 'activeTab'],
            },
            background=background)

        extension.startup()
        extension.await_message('ready')

        # The first tab's context menu.
        menu = head.open_tab_context_menu(self, 0)
        menu_item = menu.by_label('menu item on tab')
        self.assertTrue(menu_item, "the menu has the add-on's item")
        head.close_extension_context_menu(self, menu_item[0])
        extension.await_message('onCommand_on_tab_click')

        extension.unload()

        # A tab for the next task, as Firefox's window keeps its first.
        self.open_tab('about:blank')
        self.browser.close_target(tab1)
        self.browser.close_target(tab2)

    def test_01_active_tab_for_tab_menu(self):
        self.open_two_tabs_and_open_tab_menu('''async function onTabMenuClicked(info, tab) {
          browser.test.assertEq(0, tab.index, "Expected a menu on the first tab.");

          try {
            let [actualUrl] = await browser.tabs.executeScript(tab.id, {
              code: "document.URL",
            });
            browser.test.assertEq(
              tab.url,
              actualUrl,
              "Content script to execute in the first tab"
            );
            // (the activeTab permission should have been granted to the first tab.)
          } catch (e) {
            browser.test.fail(
              `Unexpected error in executeScript: ${e} :: ${e.stack}`
            );
          }
        }''')

    def test_02_no_active_tab_for_current_tab(self):
        self.open_two_tabs_and_open_tab_menu('''async function onTabMenuClicked(info, tab) {
          const PAGE_URL =
            "http://mochi.test:8888/browser/browser/components/extensions/test/browser/context.html";
          browser.test.assertEq(0, tab.index, "Expected a menu on the first tab.");
          browser.test.assertEq(
            PAGE_URL,
            tab.url,
            "Expected tab.url to be available for the first tab"
          );

          let [tab2] = await browser.tabs.query({ windowId: tab.windowId, index: 1 });
          browser.test.assertTrue(tab2.active, "The second tab should be focused.");
          browser.test.assertEq(
            undefined,
            tab2.url,
            "Expected tab.url to be unavailable for the second tab."
          );

          await browser.test.assertRejects(
            browser.tabs.executeScript(tab2.id, { code: "document.URL" }),
            /Missing host permission for the tab/,
            "Content script should not run in the second tab"
          );
          // (The activeTab permission was granted to the first tab, not tab2.)
        }''')
