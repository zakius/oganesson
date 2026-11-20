"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_event_order.js.

Firefox's Tools menu is, in this browser, the app menu's More tools
(head.open_tools_menu()), where an add-on's `tools_menu` items are to show
(zakius/oganesson#98). As in the menus port, a check before a click on the
item it reads ends the test when the item is missing, as Firefox's click on
a missing item does.
"""

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'


class MenusEventOrderTest(head.ContextMenuTest):

    def test_01_menus_click_event_sequence(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            background=JS('''async function background() {
              let events = [];

              browser.menus.onShown.addListener(() => {
                events.push("onShown");
              });
              browser.menus.onHidden.addListener(() => {
                events.push("onHidden");
                browser.test.sendMessage("event_sequence", events);
                events.length = 0;
              });

              browser.menus.create({
                title: "item in page menu",
                contexts: ["page"],
                onclick() {
                  events.push("onclick parameter of page menu item");
                },
              });
              browser.menus.create(
                {
                  title: "item in tools menu",
                  contexts: ["tools_menu"],
                  onclick() {
                    events.push("onclick parameter of tools_menu menu item");
                  },
                },
                () => {
                  // The menus creation requests are expected to be handled in-order.
                  // So when the callback for the last menu creation request is called,
                  // we can assume that all menus have been registered.
                  browser.test.sendMessage("created menus");
                }
              );
            }'''),
            manifest={
                'permissions': ['menus'],
            })
        extension.startup()
        # Waiting for events and menu items to be registered.
        extension.await_message('created menus')

        def verify_results(menu_type):
            # Getting menu event info...
            events = extension.await_message('event_sequence')
            self.is_(events,
                     ['onShown', f'onclick parameter of {menu_type} menu item', 'onHidden'],
                     'Expected order of menus events')

        # Opening and closing page menu.
        menu = head.open_context_menu(self, tab, 'body')
        menuitem = menu.by_label('item in page menu')
        self.assertTrue(menuitem, 'Page menu item should exist')
        head.close_extension_context_menu(self, menuitem[0])
        verify_results('page')

        # Opening and closing tools menu.
        menu = head.open_tools_menu(self)
        menuitem = menu.by_label('item in tools menu')
        self.assertTrue(menuitem, 'Tools menu item should exist')
        head.close_extension_context_menu(self, menuitem[0])
        verify_results('tools_menu')

        extension.unload()
        self.browser.close_target(tab)
