"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_srcUrl_redirect.js.

redirect_to.sjs is head.py's route, which always sends the browser to
ctxmenu-image.png."""

from firefox import head
from extension_test_utils import JS, FirefoxTest


class ContextMenusSrcUrlRedirectTest(FirefoxTest):
    hosts = ('mochi.test',)
    routes = head.ROUTES

    def test_srcUrl_of_redirected_image(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function background() {
              browser.contextMenus.onClicked.addListener(info => {
                browser.test.assertEq(
                  "before_redir",
                  info.menuItemId,
                  "Expected menu item matched for pre-redirect URL"
                );
                browser.test.assertEq("image", info.mediaType, "Expected mediaType");
                browser.test.assertEq(
                  "http://mochi.test:8888/browser/browser/components/extensions/test/browser/redirect_to.sjs?ctxmenu-image.png",
                  info.srcUrl,
                  "Expected srcUrl"
                );
                browser.test.sendMessage("contextMenus_onClicked");
              });
              browser.contextMenus.create({
                id: "before_redir",
                title: "MyMenu",
                targetUrlPatterns: ["*://*/*redirect_to.sjs*"],
              });
              browser.contextMenus.create(
                {
                  id: "after_redir",
                  title: "MyMenu",
                  targetUrlPatterns: ["*://*/*/ctxmenu-image.png*"],
                },
                () => {
                  browser.test.sendMessage("menus_setup");
                }
              );
            }'''))
        extension.startup()
        extension.await_message('menus_setup')

        browser = self.open_tab(f'{head.BASE}context_with_redirect.html')
        try:
            # Verify that the image has been loaded, which implies that the redirect has
            # been followed.
            img_width = browser.eval('document.getElementById("img_that_redirects").naturalWidth')
            self.assertEqual(img_width, 100, 'Image has been loaded')

            menu = head.open_context_menu(self, browser, '#img_that_redirects')
            items = menu.by_label('MyMenu')
            self.assertEqual(len(items), 1, 'Only one menu item should have been matched')

            head.close_extension_context_menu(self, items[0])
            extension.await_message('contextMenus_onClicked')
        finally:
            self.browser.close_target(browser)

        extension.unload()
