"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_radioGroups.js.

A menu item's checked state is head.py's Menu.is_checked(). The menu doesn't
show an item's label as an attribute of its own: the port reads the radio
items by their labels in the order they show."""

from firefox import head
from extension_test_utils import JS


class ContextMenusRadioGroupsTest(head.ContextMenuTest):

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
                title: "radio-group-1",
                type: "radio",
                checked: true,
              });

              browser.contextMenus.create({
                type: "separator",
              });

              browser.contextMenus.create({
                title: "radio-group-2",
                type: "radio",
              });

              browser.contextMenus.create({
                title: "radio-group-2",
                type: "radio",
              });

              browser.test.notifyPass("contextmenus-radio-groups");
            }'''))

        extension.startup()
        extension.await_finish('contextmenus-radio-groups')

        def confirm_radio_group_states(extension_menu_root, expected_states):
            # Firefox's test throws on a missing submenu too.
            self.assertIsNotNone(extension_menu_root, "the add-on's submenu")
            radio_items = extension_menu_root.checkable()
            radio_group1 = extension_menu_root.by_label('radio-group-1')
            radio_group2 = extension_menu_root.by_label('radio-group-2')

            self.assertEqual(len(radio_items), 3,
                             'there should be 3 radio items in the context menu')
            self.assertEqual(len(radio_group1), 1,
                             'the first radio group should only have 1 radio item')
            self.assertEqual(len(radio_group2), 2,
                             'the second radio group should only have 2 radio items')

            self.assertEqual(extension_menu_root.is_checked(radio_group1[0]), expected_states[0],
                             f'radio item 1 has state (checked={expected_states[0]})')
            self.assertEqual(extension_menu_root.is_checked(radio_group2[0]), expected_states[1],
                             f'radio item 2 has state (checked={expected_states[1]})')
            self.assertEqual(extension_menu_root.is_checked(radio_group2[1]), expected_states[2],
                             f'radio item 3 has state (checked={expected_states[2]})')

            return radio_items

        def confirm_on_click_data(on_click_data, id, was, checked):
            self.assertEqual(on_click_data['wasChecked'], was,
                             f"radio item {id} was {'' if was else 'not '}checked before the click")
            self.assertEqual(on_click_data['checked'], checked,
                             f"radio item {id} is {'' if checked else 'not '}checked after the click")

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        items = confirm_radio_group_states(extension_menu_root, [True, False, False])
        head.close_extension_context_menu(self, items[1])

        result = extension.await_message('contextmenus-click')
        confirm_on_click_data(result, 2, False, True)

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        items = confirm_radio_group_states(extension_menu_root, [True, True, False])
        head.close_extension_context_menu(self, items[2])

        result = extension.await_message('contextmenus-click')
        confirm_on_click_data(result, 3, False, True)

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        items = confirm_radio_group_states(extension_menu_root, [True, False, True])
        head.close_extension_context_menu(self, items[0])

        result = extension.await_message('contextmenus-click')
        confirm_on_click_data(result, 1, True, True)

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        items = confirm_radio_group_states(extension_menu_root, [True, False, True])
        head.close_extension_context_menu(self, items[0])

        result = extension.await_message('contextmenus-click')
        confirm_on_click_data(result, 1, True, True)

        extension.unload()
        self.browser.close_target(tab1)
