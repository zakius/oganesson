"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_targetElement_extension.js.

The popup opens with a real click on the add-on's toolbar button
(Browser.open_popup()), and its context menu with a right click in it, as
head.open_context_menu_in_sidebar() makes one; closeBrowserAction() closes
the popup. The sidebar task's sidebar is the side panel, where an add-on's
`sidebar_action` page is to show (zakius/oganesson#103), as in the viewType
port.
"""

from firefox import head
from extension_test_utils import JS

TAB_HTML = '<!DOCTYPE html><meta charset="utf-8"><button>Button in tab</button>'


class MenusTargetElementExtensionTest(head.ContextMenuTest):

    def test_01_getTargetElement_in_extension_tab(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            files={
                'tab.html': TAB_HTML,
            },
            background=JS('''async function background() {
              browser.menus.onShown.addListener(info => {
                let elem = browser.menus.getTargetElement(info.targetElementId);
                browser.test.assertEq(
                  null,
                  elem,
                  "should not get element of tab content in background"
                );

                // By using getViews() here, we verify that the targetElementId can
                // synchronously be mapped to a valid element in a different tab
                // during the onShown event.
                let [tabGlobal] = browser.extension.getViews({ type: "tab" });
                elem = tabGlobal.browser.menus.getTargetElement(info.targetElementId);
                browser.test.assertEq(
                  "BUTTON",
                  elem.tagName,
                  "should get element in tab content"
                );
                browser.test.sendMessage("elementChecked");
              });

              browser.tabs.create({ url: "tab.html" });
            }'''))

        extension.startup()
        # Must wait for the tab to have loaded completely before calling openContextMenu.
        tab = head.extension_tab(self, extension, 'tab.html')
        head.open_context_menu(self, tab, 'button')
        extension.await_message('elementChecked')
        head.close_context_menu(self)

        # Unloading the extension will automatically close the extension's tab.html
        extension.unload()

    def test_02_getTargetElement_in_extension_tab_on_click(self):
        # Similar to getTargetElement_in_extension_tab, except we check whether
        # calling getTargetElement in onClicked results in the expected behavior.
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            files={
                'tab.html': TAB_HTML,
            },
            background=JS('''async function background() {
              browser.menus.onClicked.addListener(info => {
                let [tabGlobal] = browser.extension.getViews({ type: "tab" });
                let elem = tabGlobal.browser.menus.getTargetElement(info.targetElementId);
                browser.test.assertEq(
                  "BUTTON",
                  elem.tagName,
                  "should get element in tab content on click"
                );
                browser.test.sendMessage("elementClicked");
              });

              browser.menus.create({ title: "click here" }, () => {
                browser.tabs.create({ url: "tab.html" });
              });
            }'''))

        extension.startup()
        tab = head.extension_tab(self, extension, 'tab.html')
        menu = head.open_context_menu(self, tab, 'button')
        menu_item = menu.by_label('click here')
        self.assertTrue(menu_item, 'the menu has the item "click here"')
        head.close_extension_context_menu(self, menu_item[0])
        extension.await_message('elementClicked')

        extension.unload()

    def test_03_getTargetElement_in_browserAction_popup(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
                'browser_action': {
                    'default_popup': 'popup.html',
                    'default_area': 'navbar',
                },
            },
            files={
                'popup.html': '<!DOCTYPE html><meta charset="utf-8"><button>Button in popup</button>',
            },
            background=JS('''async function background() {
              browser.menus.onShown.addListener(info => {
                let elem = browser.menus.getTargetElement(info.targetElementId);
                browser.test.assertEq(
                  null,
                  elem,
                  "should not get element of popup content in background"
                );

                let [popupGlobal] = browser.extension.getViews({ type: "popup" });
                elem = popupGlobal.browser.menus.getTargetElement(info.targetElementId);
                browser.test.assertEq(
                  "BUTTON",
                  elem.tagName,
                  "should get element in popup content"
                );
                browser.test.sendMessage("popupChecked");
              });

              // Ensure that onShown is registered (workaround for bug 1300234):
              await browser.menus.removeAll();
              browser.test.sendMessage("ready");
            }'''))

        extension.startup()
        extension.await_message('ready')

        popup = self.browser.open_popup(extension.id)
        head.open_context_menu_in_sidebar(self, popup, 'button')
        extension.await_message('popupChecked')
        head.close_context_menu(self)
        self.browser.close_target(popup)

        extension.unload()

    def test_04_getTargetElement_in_sidebar_panel(self):
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
                  <button>Button in sidebar</button>
                  <script src="sidebar.js"></script>
                ''',
                'sidebar.js': JS('''async function sidebarJs() {
                  browser.menus.onShown.addListener(info => {
                    let expected = document.querySelector("button");
                    let elem = browser.menus.getTargetElement(info.targetElementId);
                    browser.test.assertEq(
                      expected,
                      elem,
                      "should get element in sidebar content"
                    );
                    browser.test.sendMessage("done");
                  });

                  // Ensure that onShown is registered (workaround for bug 1300234):
                  await browser.menus.removeAll();
                  browser.test.sendMessage("ready");
                }'''),
            })

        extension.startup()
        extension.await_message('ready')

        sidebar = self.browser.page(f'chrome-extension://{extension.id}/sidebar.html')
        head.open_context_menu_in_sidebar(self, sidebar, 'button')
        extension.await_message('done')
        head.close_context_menu(self)

        extension.unload()
