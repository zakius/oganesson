"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_browserAction_getUserSettings.html.

Firefox puts a new add-on's button in the add-ons panel: the port turns off
this browser's setting that pins new extensions (head.NOT_PINNED_BY_DEFAULT).
"""

from firefox import head
from extension_test_utils import JS, FirefoxTest

BACKGROUND = JS('''async function background() {
  let { manifest_version } = await browser.runtime.getManifest();
  let action = browser.browserAction;
  if (manifest_version === 3) {
    action = browser.action;
  }
  let userSettings = await action.getUserSettings();

  if (navigator.userAgent.includes("Android")) {
    browser.test.assertDeepEq({}, userSettings, "userSettings should return an empty object on Android")
  } else {
    browser.test.assertFalse(
      userSettings.isOnToolbar,
      "isOnToolbar should be false when no default_area is specified in manifest.json"
    );
  }
  await browser.test.notifyPass("getUserSettings");
}''')


class BrowserActionGetUserSettingsTest(FirefoxTest):
    prefs = head.NOT_PINNED_BY_DEFAULT

    def test_01_browserAction_getUserSettings(self):
        extension = self.load_extension(
            manifest={'manifest_version': 2, 'browser_action': {}}, background=BACKGROUND)
        extension.startup()
        extension.await_finish('getUserSettings')
        extension.unload()

    def test_02_action_getUserSettings(self):
        extension = self.load_extension(
            manifest={'manifest_version': 3, 'action': {}}, background=BACKGROUND)
        extension.startup()
        extension.await_finish('getUserSettings')
        extension.unload()
