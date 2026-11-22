"""Port of Firefox's
browser/components/extensions/test/xpcshell/test_ext_pageAction_shutdown.js.

The add-on is Firefox's, as it is. Firefox's PageActions' `pinnedToUrlbar` is
the page action's place in the location bar: its button there, shown or
hidden (pinned_to_urlbar()). Firefox's restart of the add-on
manager is a restart of the browser (restart_browser()), and
extension.awaitStartup() waits for the add-on to be enabled again. Left out:
PageActions.init() and _reset(), which start and clear Firefox's page actions
module, and the test's own `action.pinnedToUrlbar = false`: neither Firefox
nor this browser lets the user unpin a page action from the location bar, so
the check after it is the one after the first restart.
"""

import json

from extension_test_utils import FirefoxTest
from harness import wait_for

PINNED = 'pinnedToUrlbar: the page action has its button in the location bar'


def pinned_to_urlbar(test, extension):
    """PageActions.actionForID(makeWidgetId(extension.id)).pinnedToUrlbar:
    the add-on's page action has its button in the location bar, which shows
    on the tabs where the page action is shown. This add-on doesn't show it,
    so the button is there hidden."""
    return bool(test.browser.views('FirefoxPageActionView', ExtensionId=extension.id))


def await_startup(test, extension):
    """extension.awaitStartup(): the add-on, which has no background, is
    enabled after the restart."""
    page = test.open_tab('chrome://extensions')
    try:
        wait_for(lambda: page.eval(f'chrome.management.get({json.dumps(extension.id)})'
                                   '.then(e => e.enabled).catch(() => false)'),
                 what='the add-on to start')
    finally:
        test.browser.close_target(page)


class PageActionShutdownTest(FirefoxTest):

    def test_01_app_shutdown(self):
        extension = self.load_extension(
            use_addon_manager='permanent',
            manifest={
                'page_action': {
                    'default_title': 'test_ext_pageAction_shutdown.js',
                    'browser_style': False,
                },
            })
        extension.startup()

        # Its pinnedToUrlbar should have been initialized to true when it's
        # created.
        self.assertTrue(pinned_to_urlbar(self, extension), PINNED)

        # Simulate restarting the app without first unloading the extension.
        self.restart_browser()
        await_startup(self, extension)

        # Its pinnedToUrlbar should remain true.
        self.assertTrue(pinned_to_urlbar(self, extension), PINNED)

        # Simulate restarting the app again without first unloading the
        # extension.
        self.restart_browser()
        await_startup(self, extension)

        self.assertTrue(pinned_to_urlbar(self, extension), PINNED)

        # Now unload the extension and quit the app.
        extension.unload()
