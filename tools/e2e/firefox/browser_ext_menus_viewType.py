"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_viewType.js.

The sidebar task's sidebar is the side panel, where an add-on's
`sidebar_action` page is to show (zakius/oganesson#103): head.py's
open_context_menu_in_sidebar() right-clicks in that page."""

from firefox import head
from extension_test_utils import JS


class MenusViewTypeTest(head.ContextMenuTest):

    def test_01_extension_tab_view_type(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            files={
                'tab.html': '<!DOCTYPE html><meta charset="utf-8"><script src="tab.js"></script>',
                'tab.js': 'browser.test.sendMessage("ready");',
            },
            background=JS('''async function background() {
              browser.menus.onShown.addListener(info => {
                browser.test.assertEq(
                  "tabonly",
                  info.menuIds.join(","),
                  "Expected menu items"
                );
                browser.test.sendMessage("shown");
              });
              browser.menus.onClicked.addListener(info => {
                browser.test.assertEq("tab", info.viewType, "Expected viewType");
                browser.test.sendMessage("clicked");
              });

              browser.menus.create({
                id: "sidebaronly",
                title: "sidebar-only",
                viewTypes: ["sidebar"],
              });
              browser.menus.create(
                { id: "tabonly", title: "click here", viewTypes: ["tab"] },
                () => {
                  browser.tabs.create({ url: "tab.html" });
                }
              );
            }'''))

        extension.startup()
        extension.await_message('ready')
        tab = head.extension_tab(self, extension, 'tab.html')
        # Firefox clicks at the page's corner, as tab.html has no #img1.
        menu = head.open_whole_context_menu(self, tab)
        extension.await_message('shown')

        items = menu.by_label('click here')
        self.assertTrue(items, 'the menu has the item "click here"')
        head.close_extension_context_menu(self, items[0])
        extension.await_message('clicked')

        # Unloading the extension will automatically close the extension's tab.html
        extension.unload()

    def test_02_sidebar_panel_view_type(self):
        extension = self.load_extension(
            use_addon_manager='temporary',  # To automatically show sidebar on load.
            manifest={
                'permissions': ['menus'],
                'sidebar_action': {
                    'default_panel': 'sidebar.html',
                },
            },
            files={
                'sidebar.html': '''
                  <!DOCTYPE html><meta charset="utf-8">
                  <script src="sidebar.js"></script>
                ''',
                'sidebar.js': JS('''async function sidebarJs() {
                  browser.menus.onShown.addListener(info => {
                    browser.test.assertEq(
                      "sidebaronly",
                      info.menuIds.join(","),
                      "Expected menu items"
                    );
                    browser.test.assertEq("sidebar", info.viewType, "Expected viewType");
                    browser.test.sendMessage("shown");
                  });

                  // Create menus and change their viewTypes using menus.update.
                  browser.menus.create({
                    id: "sidebaronly",
                    title: "sidebaronly",
                    viewTypes: ["tab"],
                  });
                  browser.menus.create({
                    id: "tabonly",
                    title: "tabonly",
                    viewTypes: ["sidebar"],
                  });
                  await browser.menus.update("sidebaronly", { viewTypes: ["sidebar"] });
                  await browser.menus.update("tabonly", { viewTypes: ["tab"] });
                  browser.test.sendMessage("ready");
                }'''),
            })

        extension.startup()
        extension.await_message('ready')

        sidebar = self.browser.page(f'chrome-extension://{extension.id}/sidebar.html')
        head.open_context_menu_in_sidebar(self, sidebar)
        extension.await_message('shown')
        head.close_context_menu(self)

        extension.unload()
