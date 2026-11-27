"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_browserAction_popup_resize.js.

The add-ons' code is Firefox's, as it is. Their buttons start on the toolbar,
as `default_area: "navbar"` puts them in Firefox: this browser pins a new
add-on's button. openBrowserActionPanel() is a real click on it, and
closeBrowserAction() closes the popup (head_browserAction). Firefox's popup
browser and its size are the popup's web view here
(head_pageAction.content_dimensions(), alter_content()), and the popup
panel's state "closed" is the popup bubble gone. testPopupSize() is
head_browserAction.test_popup_size(), whose docstring says how the add-ons
panel and its popup are this browser's.
"""

from firefox import head_browserAction, head_pageAction
from extension_test_utils import FirefoxTest


class BrowserActionPopupResizeTest(FirefoxTest):

    def test_01_browser_action_popup_resize(self):
        extension = self.load_extension(
            manifest={
                'browser_action': {
                    'default_popup': 'popup.html',
                    'default_area': 'navbar',
                    'browser_style': True,
                },
            },

            files={
                'popup.html':
                    '<!DOCTYPE html><html><head><meta charset="utf-8"></head></html>',
            })

        extension.startup()

        browser = head_browserAction.open_browser_action_panel(self, extension, pinned=True)

        def check_size(expected):
            dims = head_pageAction.content_dimensions(self, browser)

            self.check(abs(dims['window']['innerHeight'] - expected) <= 1,
                       f'Panel window should be {expected}px tall '
                       f"(was {dims['window']['innerHeight']})")
            self.is_(dims['body']['clientHeight'], dims['body']['scrollHeight'],
                     'Panel body should be tall enough to fit its contents')

            # Tolerate if it is 1px too wide, as that may happen with the current resizing method.
            self.check(abs(dims['window']['innerWidth'] - expected) <= 1,
                       f'Panel window should be {expected}px wide - '
                       f"Actual: {dims['window']['innerWidth']}")
            self.is_(dims['body']['clientWidth'], dims['body']['scrollWidth'],
                     'Panel body should be wide enough to fit its contents')

        set_size = '''function setSize(size) {
    content.document.body.style.height = `${size}px`;
    content.document.body.style.width = `${size}px`;
  }'''

        sizes = [200, 400, 300]

        for size in sizes:
            head_pageAction.alter_content(self, browser, set_size, size)
            check_size(size)

        head_browserAction.close_browser_action(self, extension)
        self.check(head_pageAction.popup_view(self) is None,
                   'browserAction popup has been closed')

        extension.unload()

    def test_02_browser_action_menu_resize_standards(self):
        head_browserAction.test_popup_size(self, True)

    def test_03_browser_action_menu_resize_quirks(self):
        head_browserAction.test_popup_size(self, False)
