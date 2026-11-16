"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_uninstall.js.

Firefox's top-level menu of an add-on ("top-level-menu") is, in this
browser, the item with the add-on's name, here Firefox's default name."""

from firefox import head
from extension_test_utils import JS


class ContextMenusUninstallTest(head.ContextMenuTest):

    def test_01(self):
        tab1 = self.open_tab(f'{head.BASE}context.html')

        # Install an extension.
        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function () {
              browser.contextMenus.create({ title: "a" });
              browser.contextMenus.create({ title: "b" });
              browser.test.notifyPass("contextmenus-icons");
            }'''))

        extension.startup()
        extension.await_finish('contextmenus-icons')

        # Open the context menu.
        context_menu = head.open_context_menu(self, tab1, '#img1')

        # Confirm that the extension menu item exists.
        top_level_extension_menu_items = context_menu.by_label('Generated extension')
        self.assertEqual(len(top_level_extension_menu_items), 1,
                         'the top level extension menu item exists')

        head.close_context_menu(self)

        # Uninstall the extension.
        extension.unload()

        # Open the context menu.
        context_menu = head.open_context_menu(self, tab1, '#img1')

        # Confirm that the extension menu item has been removed.
        top_level_extension_menu_items = context_menu.by_label('Generated extension')
        self.assertEqual(len(top_level_extension_menu_items), 0,
                         'no top level extension menu items should exist')

        head.close_context_menu(self)

        # Install a new extension.
        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function () {
              browser.contextMenus.create({ title: "c" });
              browser.contextMenus.create({ title: "d" });
              browser.test.notifyPass("contextmenus-uninstall-second-extension");
            }'''))

        extension.startup()
        extension.await_finish('contextmenus-uninstall-second-extension')

        # Open the context menu.
        context_menu = head.open_context_menu(self, tab1, '#img1')

        # Confirm that only the new extension menu item is in the context menu.
        top_level_extension_menu_items = context_menu.by_label('Generated extension')
        self.assertEqual(len(top_level_extension_menu_items), 1,
                         'only one top level extension menu item should exist')

        # Close the context menu.
        head.close_context_menu(self)

        # Uninstall the extension.
        extension.unload()

        # Open the context menu.
        context_menu = head.open_context_menu(self, tab1, '#img1')

        # Confirm that no extension menu items exist.
        top_level_extension_menu_items = context_menu.by_label('Generated extension')
        self.assertEqual(len(top_level_extension_menu_items), 0,
                         'no top level extension menu items should exist')

        head.close_context_menu(self)

        self.browser.close_target(tab1)
