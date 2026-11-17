"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_capture_secondary_click.js.

A click with Firefox's button 0, 1 or 2 is a real click with the left,
middle or right button (head.synthesize_mouse_at_center()). Left out:
AccessibilityUtils.setEnv(), Firefox's accessibility checks of its own test
clicks."""

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'


class MenusCaptureSecondaryClickTest(head.ContextMenuTest):

    def test_01_buttons(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''function background() {
              function onclick(info) {
                browser.test.sendMessage("click", info);
              }
              browser.menus.create({ title: "modify", onclick }, () => {
                browser.test.sendMessage("ready");
              });
            }'''))
        tab = self.open_tab(PAGE)

        extension.startup()
        extension.await_message('ready')

        for i in (0, 1, 2):
            menu = head.open_context_menu(self, tab)
            items = menu.by_label('modify')
            self.assertTrue(items, 'the menu has the item')
            head.close_extension_context_menu(self, items[0], {'button': i})
            info = extension.await_message('click')
            self.is_(info.get('button'), i, f'Button value should be {i}')

        self.browser.close_target(tab)
        extension.unload()

    def test_02_submenu(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''function background() {
              browser.menus.onClicked.addListener(info => {
                browser.test.assertEq("child", info.menuItemId, "expected menu item");
                browser.test.sendMessage("clicked_button", info.button);
              });
              browser.menus.create({
                id: "parent",
                title: "parent",
              });
              browser.menus.create(
                {
                  id: "child",
                  parentId: "parent",
                  title: "child",
                },
                () => browser.test.sendMessage("ready")
              );
            }'''))
        tab = self.open_tab(PAGE)

        extension.startup()
        extension.await_message('ready')

        for button in (0, 1, 2):
            menu = head.open_context_menu(self, tab)
            parent_items = menu.by_label('parent')
            self.assertTrue(parent_items, 'the menu has the parent item')
            submenu = head.open_submenu(self, parent_items[0])
            child_item = submenu.items[0]
            # This should not trigger a click event.
            head.synthesize_mouse_at_center(self, parent_items[0], button)
            head.close_extension_context_menu(self, child_item, {'button': button})
            self.is_(extension.await_message('clicked_button'), button, 'Expected button')

        self.browser.close_target(tab)
        extension.unload()

    def test_03_disabled_item(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''function background() {
              browser.menus.onHidden.addListener(() =>
                browser.test.sendMessage("onHidden")
              );
              browser.menus.create(
                {
                  title: "disabled_item",
                  enabled: false,
                  onclick(info) {
                    browser.test.fail(
                      `Unexpected click on disabled_item, button=${info.button}`
                    );
                  },
                },
                () => browser.test.sendMessage("ready")
              );
            }'''))
        tab = self.open_tab(PAGE)

        extension.startup()
        extension.await_message('ready')

        for button in (0, 1, 2):
            menu = head.open_context_menu(self, tab)
            items = menu.by_label('disabled_item')
            self.assertTrue(items, 'the menu has the item')
            # The click on a disabled item, which must not come through.
            head.synthesize_mouse_at_center(self, items[0], button)
            head.close_context_menu(self)
            extension.await_message('onHidden')

        self.browser.close_target(tab)
        extension.unload()
