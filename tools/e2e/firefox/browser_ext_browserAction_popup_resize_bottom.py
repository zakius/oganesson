"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_browserAction_popup_resize_bottom.js.

The add-on's code is Firefox's, as it is (head_browserAction.test_popup_size(),
whose docstring says how the add-ons panel and its popup are this browser's).
BrowserTestUtils.openNewBrowserWindow() and closeWindow() are head's, and the
window's resizeTo() and moveTo() are DevTools' Browser.setWindowBounds(). As
in Firefox, the window may not go where it is asked (this browser's window has
a minimum size), and the test goes on from where it is.
"""

import time

from firefox import head, head_browserAction
from extension_test_utils import FirefoxTest


class BrowserActionPopupResizeBottomTest(FirefoxTest):

    # Test that we still make reasonable maximum size calculations when the window
    # is close enough to the bottom of the screen that the menu panel opens above,
    # rather than below, its button.
    def test_01_browser_action_menu_resize_bottom_arrow(self):
        width = 800
        height = 80

        screen = head_browserAction.window_screen(self)
        left = screen['availLeft'] + screen['availWidth'] - width
        top = screen['availTop'] + screen['availHeight'] - height

        win = head.open_new_browser_window(self)

        def window_bounds():
            return self.browser.browser_call('Browser.getWindowBounds', windowId=win)['bounds']

        # Trying to position in (left, top)

        self.browser.browser_call('Browser.setWindowBounds', windowId=win,
                                  bounds={'width': width, 'height': height})

        # Sometimes we run into problems on Linux with resizing being asynchronous
        # and window managers not allowing us to move the window so that any part of
        # it is off-screen, so we need to try more than once.
        for _ in range(20):
            self.browser.browser_call('Browser.setWindowBounds', windowId=win,
                                      bounds={'left': left, 'top': top})

            bounds = window_bounds()
            if bounds['left'] == left and bounds['top'] == top:
                break

            time.sleep(0.1)

        head_browserAction.test_popup_size(self, True, 'bottom')

        head.close_window(self, win)
