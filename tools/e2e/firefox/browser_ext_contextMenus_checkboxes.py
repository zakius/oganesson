"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_checkboxes.js.

This browser puts an add-on's single checkbox item in a submenu of its own,
as Firefox does on Linux, the branch that the port checks. A menu item's
checked state is head.py's Menu.is_checked()."""

from firefox import head
from extension_test_utils import JS


class ContextMenusCheckboxesTest(head.ContextMenuTest):

    def test_01(self):
        tab1 = self.open_tab(f'{head.BASE}context.html')

        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function () {
              // Report onClickData info back.
              browser.contextMenus.onClicked.addListener(info => {
                browser.test.sendMessage("contextmenus-click", info);
              });

              browser.contextMenus.create({
                title: "Checkbox",
                type: "checkbox",
              });

              browser.test.sendMessage("single-contextmenu-item-added");

              browser.test.onMessage.addListener(msg => {
                if (msg !== "add-additional-menu-items") {
                  return;
                }

                browser.contextMenus.create({
                  type: "separator",
                });

                browser.contextMenus.create({
                  title: "Checkbox",
                  type: "checkbox",
                  checked: true,
                });

                browser.contextMenus.create({
                  title: "Checkbox",
                  type: "checkbox",
                });

                browser.test.notifyPass("contextmenus-checkboxes");
              });
            }'''))

        extension.startup()

        extension.await_message('single-contextmenu-item-added')

        def test_single_checkbox_item():
            extension_menu_root = head.open_extension_context_menu(self, tab1)

            # On Linux, the single menu item should be contained in a submenu.
            self.assertIsNotNone(extension_menu_root, "the add-on's submenu")
            items = extension_menu_root.checkable()
            self.assertEqual(len(items), 1, 'single checkbox should be in the submenu on Linux')
            head.close_context_menu(self)

        test_single_checkbox_item()

        extension.send_message('add-additional-menu-items')
        extension.await_finish('contextmenus-checkboxes')

        def confirm_checkbox_states(extension_menu_root, expected_states):
            # Firefox's test throws on a missing submenu too.
            self.assertIsNotNone(extension_menu_root, "the add-on's submenu")
            checkbox_items = extension_menu_root.checkable()

            self.assertEqual(len(checkbox_items), 3,
                             'there should be 3 checkbox items in the context menu')

            for number, (item, expected) in enumerate(zip(checkbox_items, expected_states), 1):
                self.assertEqual(extension_menu_root.is_checked(item), expected,
                                 f'checkbox item {number} has state (checked={expected})')

            return checkbox_items

        def confirm_on_click_data(on_click_data, id, was, checked):
            self.assertEqual(on_click_data['wasChecked'], was,
                             f"checkbox item {id} was {'' if was else 'not '}checked before the click")
            self.assertEqual(on_click_data['checked'], checked,
                             f"checkbox item {id} is {'' if checked else 'not '}checked after the click")

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        items = confirm_checkbox_states(extension_menu_root, [False, True, False])
        head.close_extension_context_menu(self, items[0])

        result = extension.await_message('contextmenus-click')
        confirm_on_click_data(result, 1, False, True)

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        items = confirm_checkbox_states(extension_menu_root, [True, True, False])
        head.close_extension_context_menu(self, items[2])

        result = extension.await_message('contextmenus-click')
        confirm_on_click_data(result, 3, False, True)

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        items = confirm_checkbox_states(extension_menu_root, [True, True, True])
        head.close_extension_context_menu(self, items[0])

        result = extension.await_message('contextmenus-click')
        confirm_on_click_data(result, 1, True, False)

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        items = confirm_checkbox_states(extension_menu_root, [False, True, True])
        head.close_extension_context_menu(self, items[2])

        result = extension.await_message('contextmenus-click')
        confirm_on_click_data(result, 3, True, False)

        extension.unload()
        self.browser.close_target(tab1)
