"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_browserAction_onUserSettingsChanged.js.

pinToToolbar() pins the add-on to the toolbar or unpins it into the
Extensions menu (head.pin_to_toolbar()), where Firefox moves its button to
the navigation bar or to the add-ons panel. Firefox puts a new add-on's
button in the add-ons panel unless `default_area` names a toolbar: the
port turns off this browser's setting that pins new extensions
(head.NOT_PINNED_BY_DEFAULT).
"""

import json

from firefox import head
from extension_test_utils import JS, FirefoxTest

BACKGROUND = '''async function background(test) {
  let action = browser.action || browser.browserAction;

  async function pinToToolbar(shouldPinToToolbar) {
    const identifier = `${shouldPinToToolbar ? "pin-to-toolbar" : "unpin-from-toolbar"}-${crypto.randomUUID()}`;

    const promise = new Promise(resolve => {
      function listener(id) {
        if (id !== identifier) {
          browser.test.fail(`unexpected message received: ${id}`);
        }

        browser.test.onMessage.removeListener(listener);
        resolve(id);
      }
      browser.test.onMessage.addListener(listener);
    });

    browser.test.sendMessage("pinToToolbar", {
      identifier,
      shouldPinToToolbar,
    });

    await promise;
  }

  function waitForUserSettingsChanged() {
    return new Promise(resolve => {
      function listener(changed) {
        action.onUserSettingsChanged.removeListener(listener);
        resolve(changed);
      }
      action.onUserSettingsChanged.addListener(listener);
    });
  }

  let tests = {};

  tests.onUserSettingsChanged = async function () {
    let userSettingsChanged = waitForUserSettingsChanged();
    await pinToToolbar(true);
    let userSettings = await userSettingsChanged;
    browser.test.assertTrue(
      userSettings.isOnToolbar,
      "isOnToolbar should be true after pinning to toolbar"
    );
    browser.test.assertDeepEq(
      userSettings,
      await action.getUserSettings(),
      "The output of action.getUserSettings() and the onUserSettingsChanged event should be identical"
    );

    userSettingsChanged = waitForUserSettingsChanged();
    await pinToToolbar(false);
    userSettings = await userSettingsChanged;
    browser.test.assertFalse(
      userSettings.isOnToolbar,
      "isOnToolbar should be false after unpinning from toolbar"
    );
    browser.test.assertDeepEq(
      userSettings,
      await action.getUserSettings(),
      "The output of action.getUserSettings() and the onUserSettingsChanged event should be identical"
    );

    userSettingsChanged = waitForUserSettingsChanged();
    await pinToToolbar(true);
    userSettings = await userSettingsChanged;
    browser.test.assertTrue(
      userSettings.isOnToolbar,
      "isOnToolbar should be true after pinning to toolbar"
    );
    browser.test.assertDeepEq(
      userSettings,
      await action.getUserSettings(),
      "The output of action.getUserSettings() and the onUserSettingsChanged event should be identical"
    );

    userSettingsChanged = waitForUserSettingsChanged();
    await pinToToolbar(false);
    userSettings = await userSettingsChanged;
    browser.test.assertFalse(
      userSettings.isOnToolbar,
      "isOnToolbar should be false after unpinning from toolbar"
    );
    browser.test.assertDeepEq(
      userSettings,
      await action.getUserSettings(),
      "The output of action.getUserSettings() and the onUserSettingsChanged event should be identical"
    );

    await browser.test.notifyPass("onUserSettingsChanged");
  };

  tests.default_area_onUserSettingsChanged = async function () {
    let userSettingsChanged = waitForUserSettingsChanged();
    await pinToToolbar(false);
    let userSettings = await userSettingsChanged;
    browser.test.assertFalse(
      userSettings.isOnToolbar,
      "isOnToolbar should be false after unpinning from toolbar"
    );
    browser.test.assertDeepEq(
      userSettings,
      await action.getUserSettings(),
      "The output of action.getUserSettings() and the onUserSettingsChanged event should be identical"
    );

    await browser.test.notifyPass("onUserSettingsChanged");
  };

  tests[test]();
}'''


class BrowserActionOnUserSettingsChangedTest(FirefoxTest):
    prefs = head.NOT_PINNED_BY_DEFAULT

    def load(self, manifest_version, action, test):
        extension = self.load_extension(
            manifest={'manifest_version': manifest_version, **action},
            background=JS(BACKGROUND, json.dumps(test)))

        def pin(details):
            head.pin_to_toolbar(self, extension, details['shouldPinToToolbar'])
            extension.send_message(details['identifier'])
        extension.on_message('pinToToolbar', pin)
        extension.startup()
        return extension

    def test_01_browserAction_onUserSettingsChanged(self):
        extension = self.load(2, {'browser_action': {}}, 'onUserSettingsChanged')
        extension.await_finish('onUserSettingsChanged')
        extension.unload()

    def test_02_action_onUserSettingsChanged(self):
        extension = self.load(3, {'action': {}}, 'onUserSettingsChanged')
        extension.await_finish('onUserSettingsChanged')
        extension.unload()

    def test_03_browserAction_onUserSettingsChanged_default_area(self):
        for default_area in ['navbar', 'tabstrip', 'personaltoolbar']:
            # Testing with browser_action.default_area
            extension = self.load(2, {'browser_action': {'default_area': default_area}},
                                  'default_area_onUserSettingsChanged')
            extension.await_finish('onUserSettingsChanged')
            extension.unload()

    def test_04_action_onUserSettingsChanged_default_area(self):
        for default_area in ['navbar', 'tabstrip', 'personaltoolbar']:
            # Testing with action.default_area
            extension = self.load(3, {'action': {'default_area': default_area}},
                                  'default_area_onUserSettingsChanged')
            extension.await_finish('onUserSettingsChanged')
            extension.unload()
