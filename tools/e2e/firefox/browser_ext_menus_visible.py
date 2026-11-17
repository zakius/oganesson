"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_visible.js."""

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'


class MenusVisibleTest(head.ContextMenuTest):

    def test_01_visible_false(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              browser.menus.onShown.addListener(info => {
                browser.test.assertEq(
                  "[]",
                  JSON.stringify(info.menuIds),
                  "Expected no menu items"
                );
                browser.test.sendMessage("done");
              });
              browser.menus.create({
                id: "create-visible-false",
                title: "invisible menu item",
                visible: false,
              });
              browser.menus.create({
                id: "update-without-params",
                title: "invisible menu item",
                visible: false,
              });
              await browser.menus.update("update-without-params", {});
              browser.menus.create({
                id: "update-visible-to-false",
                title: "initially visible menu item",
              });
              await browser.menus.update("update-visible-to-false", { visible: false });
              browser.test.sendMessage("ready");
            }'''))

        extension.startup()
        extension.await_message('ready')
        head.open_context_menu(self, tab)
        extension.await_message('done')
        head.close_context_menu(self)

        extension.unload()

        self.browser.close_target(tab)

    def test_02_visible_true(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              browser.menus.onShown.addListener(info => {
                browser.test.assertEq(
                  `["update-to-true"]`,
                  JSON.stringify(info.menuIds),
                  "Expected no menu items"
                );
                browser.test.sendMessage("done");
              });
              browser.menus.create({
                id: "update-to-true",
                title: "invisible menu item",
                visible: false,
              });
              await browser.menus.update("update-to-true", { visible: true });
              browser.test.sendMessage("ready");
            }'''))

        extension.startup()
        extension.await_message('ready')
        head.open_context_menu(self, tab)
        extension.await_message('done')
        head.close_context_menu(self)

        extension.unload()

        self.browser.close_target(tab)
