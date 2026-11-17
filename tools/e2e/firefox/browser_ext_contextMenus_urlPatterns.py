"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_urlPatterns.js.

Firefox's getElementsByAttribute() on the context menu reaches into the
add-on's closed submenu, so where the test reads the context menu, the port
reads it with the add-on's submenu opened (head.py's open_whole_context_menu())."""

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'


class ContextMenusUrlPatternsTest(head.ContextMenuTest):

    def test_01(self):
        tab1 = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function () {
              // Test menu items using targetUrlPatterns.
              browser.contextMenus.create({
                title: "targetUrlPatterns-patternMatches-contextAll",
                targetUrlPatterns: ["*://*/*ctxmenu-image.png", "*://*/*some-link"],
                contexts: ["all"],
              });

              browser.contextMenus.create({
                title: "targetUrlPatterns-patternMatches-contextImage",
                targetUrlPatterns: ["*://*/*ctxmenu-image.png"],
                contexts: ["image"],
              });

              browser.contextMenus.create({
                title: "targetUrlPatterns-patternMatches-contextLink",
                targetUrlPatterns: ["*://*/*some-link"],
                contexts: ["link"],
              });

              browser.contextMenus.create({
                title: "targetUrlPatterns-patternDoesNotMatch-contextAll",
                targetUrlPatterns: ["*://*/does-not-match"],
                contexts: ["all"],
              });

              browser.contextMenus.create({
                title: "targetUrlPatterns-patternDoesNotMatch-contextImage",
                targetUrlPatterns: ["*://*/does-not-match"],
                contexts: ["image"],
              });

              browser.contextMenus.create({
                title: "targetUrlPatterns-patternDoesNotMatch-contextLink",
                targetUrlPatterns: ["*://*/does-not-match"],
                contexts: ["link"],
              });

              // Test menu items using documentUrlPatterns.
              browser.contextMenus.create({
                title: "documentUrlPatterns-patternMatches-contextAll",
                documentUrlPatterns: ["*://*/*context*.html"],
                contexts: ["all"],
              });

              browser.contextMenus.create({
                title: "documentUrlPatterns-patternMatches-contextFrame",
                documentUrlPatterns: ["*://*/*context_frame.html"],
                contexts: ["frame"],
              });

              browser.contextMenus.create({
                title: "documentUrlPatterns-patternMatches-contextImage",
                documentUrlPatterns: [
                  "*://*/*context.html",
                  "http://*/url-that-does-not-match",
                ],
                contexts: ["image"],
              });

              browser.contextMenus.create({
                title: "documentUrlPatterns-patternMatches-contextLink",
                documentUrlPatterns: ["*://*/*context.html", "*://*/does-not-match"],
                contexts: ["link"],
              });

              browser.contextMenus.create({
                title: "documentUrlPatterns-patternDoesNotMatch-contextAll",
                documentUrlPatterns: ["*://*/does-not-match"],
                contexts: ["all"],
              });

              browser.contextMenus.create({
                title: "documentUrlPatterns-patternDoesNotMatch-contextImage",
                documentUrlPatterns: ["*://*/does-not-match"],
                contexts: ["image"],
              });

              browser.contextMenus.create({
                title: "documentUrlPatterns-patternDoesNotMatch-contextLink",
                documentUrlPatterns: ["*://*/does-not-match"],
                contexts: ["link"],
              });

              // Test menu items using both targetUrlPatterns and documentUrlPatterns.
              browser.contextMenus.create({
                title:
                  "documentUrlPatterns-patternMatches-targetUrlPatterns-patternMatches-contextAll",
                documentUrlPatterns: ["*://*/*context.html"],
                targetUrlPatterns: ["*://*/*ctxmenu-image.png"],
                contexts: ["all"],
              });

              browser.contextMenus.create({
                title:
                  "documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternMatches-contextAll",
                documentUrlPatterns: ["*://*/does-not-match"],
                targetUrlPatterns: ["*://*/*ctxmenu-image.png"],
                contexts: ["all"],
              });

              browser.contextMenus.create({
                title:
                  "documentUrlPatterns-patternMatches-targetUrlPatterns-patternDoesNotMatch-contextAll",
                documentUrlPatterns: ["*://*/*context.html"],
                targetUrlPatterns: ["*://*/does-not-match"],
                contexts: ["all"],
              });

              browser.contextMenus.create({
                title:
                  "documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternDoesNotMatch-contextAll",
                documentUrlPatterns: ["*://*/does-not-match"],
                targetUrlPatterns: ["*://*/does-not-match"],
                contexts: ["all"],
              });

              browser.contextMenus.create({
                title:
                  "documentUrlPatterns-patternMatches-targetUrlPatterns-patternMatches-contextImage",
                documentUrlPatterns: ["*://*/*context.html"],
                targetUrlPatterns: ["*://*/*ctxmenu-image.png"],
                contexts: ["image"],
              });

              browser.contextMenus.create({
                title:
                  "documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternMatches-contextImage",
                documentUrlPatterns: ["*://*/does-not-match"],
                targetUrlPatterns: ["*://*/*ctxmenu-image.png"],
                contexts: ["image"],
              });

              browser.contextMenus.create({
                title:
                  "documentUrlPatterns-patternMatches-targetUrlPatterns-patternDoesNotMatch-contextImage",
                documentUrlPatterns: ["*://*/*context.html"],
                targetUrlPatterns: ["*://*/does-not-match"],
                contexts: ["image"],
              });

              browser.contextMenus.create({
                title:
                  "documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternDoesNotMatch-contextImage",
                documentUrlPatterns: ["*://*/does-not-match/"],
                targetUrlPatterns: ["*://*/does-not-match"],
                contexts: ["image"],
              });

              browser.test.notifyPass("contextmenus-urlPatterns");
            }'''))

        def confirm_context_menu_items(menu, expected):
            for label, should_show in expected:
                items = menu.by_label(label)
                if should_show:
                    self.is_(len(items), 1, f'The menu item for label {label} was correctly shown')
                else:
                    self.is_(len(items), 0, f'The menu item for label {label} was correctly not shown')

        extension.startup()
        extension.await_finish('contextmenus-urlPatterns')

        extension_context_menu = head.open_extension_context_menu(self, tab1, '#img1')
        expected = [
            ('targetUrlPatterns-patternMatches-contextAll', True),
            ('targetUrlPatterns-patternMatches-contextImage', True),
            ('targetUrlPatterns-patternMatches-contextLink', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextLink', False),
            ('documentUrlPatterns-patternMatches-contextAll', True),
            ('documentUrlPatterns-patternMatches-contextImage', True),
            ('documentUrlPatterns-patternMatches-contextLink', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextLink', False),
            ('documentUrlPatterns-patternMatches-targetUrlPatterns-patternMatches-contextAll', True),
            ('documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternMatches-contextAll', False),
            ('documentUrlPatterns-patternMatches-targetUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('documentUrlPatterns-patternMatches-targetUrlPatterns-patternMatches-contextImage', True),
            ('documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternMatches-contextImage', False),
            ('documentUrlPatterns-patternMatches-targetUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternDoesNotMatch-contextImage', False),
        ]
        confirm_context_menu_items(extension_context_menu, expected)
        head.close_context_menu(self)

        context_menu = head.open_whole_context_menu(self, tab1, 'body')
        expected = [
            ('targetUrlPatterns-patternMatches-contextAll', False),
            ('targetUrlPatterns-patternMatches-contextImage', False),
            ('targetUrlPatterns-patternMatches-contextLink', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextLink', False),
            ('documentUrlPatterns-patternMatches-contextAll', True),
            ('documentUrlPatterns-patternMatches-contextImage', False),
            ('documentUrlPatterns-patternMatches-contextLink', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextLink', False),
            ('documentUrlPatterns-patternMatches-targetUrlPatterns-patternMatches-contextAll', False),
            ('documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternMatches-contextAll', False),
            ('documentUrlPatterns-patternMatches-targetUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('documentUrlPatterns-patternMatches-targetUrlPatterns-patternMatches-contextImage', False),
            ('documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternMatches-contextImage', False),
            ('documentUrlPatterns-patternMatches-targetUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('documentUrlPatterns-patternDoesNotMatch-targetUrlPatterns-patternDoesNotMatch-contextImage', False),
        ]
        confirm_context_menu_items(context_menu, expected)
        head.close_context_menu(self)

        context_menu = head.open_whole_context_menu(self, tab1, '#link1')
        expected = [
            ('targetUrlPatterns-patternMatches-contextAll', True),
            ('targetUrlPatterns-patternMatches-contextImage', False),
            ('targetUrlPatterns-patternMatches-contextLink', True),
            ('targetUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextLink', False),
            ('documentUrlPatterns-patternMatches-contextAll', True),
            ('documentUrlPatterns-patternMatches-contextImage', False),
            ('documentUrlPatterns-patternMatches-contextLink', True),
            ('documentUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextLink', False),
        ]
        confirm_context_menu_items(context_menu, expected)
        head.close_context_menu(self)

        context_menu = head.open_whole_context_menu(self, tab1, '#img-wrapped-in-link')
        expected = [
            ('targetUrlPatterns-patternMatches-contextAll', True),
            ('targetUrlPatterns-patternMatches-contextImage', True),
            ('targetUrlPatterns-patternMatches-contextLink', True),
            ('targetUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('targetUrlPatterns-patternDoesNotMatch-contextLink', False),
            ('documentUrlPatterns-patternMatches-contextAll', True),
            ('documentUrlPatterns-patternMatches-contextImage', True),
            ('documentUrlPatterns-patternMatches-contextLink', True),
            ('documentUrlPatterns-patternDoesNotMatch-contextAll', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextImage', False),
            ('documentUrlPatterns-patternDoesNotMatch-contextLink', False),
        ]
        confirm_context_menu_items(context_menu, expected)
        head.close_context_menu(self)

        context_menu = head.open_whole_context_menu(self, tab1, 'body', frame_index=0)
        expected = [
            ('documentUrlPatterns-patternMatches-contextAll', True),
            ('documentUrlPatterns-patternMatches-contextFrame', True),
        ]
        confirm_context_menu_items(context_menu, expected)
        head.close_context_menu(self)

        extension.unload()
        self.browser.close_target(tab1)
