"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_browserAction_onUserSettingsChanged.html.

Firefox puts a new add-on's button in the add-ons panel: the port turns off
this browser's setting that pins new extensions (head.NOT_PINNED_BY_DEFAULT).
"""

from firefox import head
from extension_test_utils import JS, FirefoxTest

BACKGROUND = JS('''async function background() {
  let action = browser.action || browser.browserAction;

  let listener = function () {};

  browser.test.log("Test basic functionality of action.onUserSettingsChanged event");

  action.onUserSettingsChanged.addListener(listener);
  action.onUserSettingsChanged.removeListener(listener);

  await browser.test.notifyPass("onUserSettingsChanged");
}''')


class BrowserActionOnUserSettingsChangedTest(FirefoxTest):
    prefs = head.NOT_PINNED_BY_DEFAULT

    def test_01_browserAction_onUserSettingsChanged(self):
        extension = self.load_extension(
            manifest={'manifest_version': 2, 'browser_action': {}}, background=BACKGROUND)
        extension.startup()
        extension.await_finish('onUserSettingsChanged')
        extension.unload()

    def test_02_action_onUserSettingsChanged(self):
        extension = self.load_extension(
            manifest={'manifest_version': 3, 'action': {}}, background=BACKGROUND)
        extension.startup()
        extension.await_finish('onUserSettingsChanged')
        extension.unload()
