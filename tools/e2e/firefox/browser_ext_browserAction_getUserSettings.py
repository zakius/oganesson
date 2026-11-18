"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_browserAction_getUserSettings.js.

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
  let resolvers = {};
  let tests = {};

  browser.test.onMessage.addListener(id => {
    let resolver = resolvers[id];
    browser.test.assertTrue(resolver, `Found resolver for ${id}`);
    browser.test.assertTrue(resolver.resolve, `${id} was not resolved yet`);
    resolver.resolve(id);
    resolver.resolve = null; // resolve can be used only once.
  });

  async function pinToToolbar(shouldPinToToolbar) {
    let identifier = `${
      shouldPinToToolbar ? "pin-to-toolbar" : "unpin-from-toolbar"
    }-${Object.keys(resolvers).length}`;
    resolvers[identifier] = {};
    resolvers[identifier].promise = new Promise(
      _resolve => (resolvers[identifier].resolve = _resolve)
    );
    browser.test.sendMessage("pinToToolbar", {
      identifier,
      shouldPinToToolbar,
    });
    await resolvers[identifier].promise;
  }

  let { manifest_version } = await browser.runtime.getManifest();
  let action = browser.browserAction;

  if (manifest_version === 3) {
    action = browser.action;
  }

  tests.getUserSettings = async function () {
    let userSettings = await action.getUserSettings();

    await pinToToolbar(true);
    userSettings = await action.getUserSettings();
    browser.test.assertTrue(
      userSettings.isOnToolbar,
      "isOnToolbar should be true after pinning to toolbar"
    );

    await pinToToolbar(false);
    userSettings = await action.getUserSettings();
    browser.test.assertFalse(
      userSettings.isOnToolbar,
      "isOnToolbar should be false after unpinning"
    );

    await pinToToolbar(true);
    userSettings = await action.getUserSettings();
    browser.test.assertTrue(
      userSettings.isOnToolbar,
      "isOnToolbar should be true after repinning"
    );

    await pinToToolbar(false);
    userSettings = await action.getUserSettings();
    browser.test.assertFalse(
      userSettings.isOnToolbar,
      "isOnToolbar should be false after unpinning"
    );

    await browser.test.notifyPass("getUserSettings");
  };

  tests.default_area_getUserSettings = async function () {
    let userSettings = await action.getUserSettings();

    browser.test.assertTrue(
      userSettings.isOnToolbar,
      "isOnToolbar should be true when one of ['navbar', 'tabstrip', 'personaltoolbar'] default_area is specified in manifest.json"
    );

    await pinToToolbar(false);
    userSettings = await action.getUserSettings();
    browser.test.assertFalse(
      userSettings.isOnToolbar,
      "isOnToolbar should be false after unpinning"
    );

    await browser.test.notifyPass("getUserSettings");
  };

  tests.menupanel_default_area_getUserSettings = async function () {
    let userSettings = await action.getUserSettings();

    browser.test.assertFalse(
      userSettings.isOnToolbar,
      "isOnToolbar should be false when default_area is 'menupanel' in manifest.json"
    );

    await pinToToolbar(true);
    userSettings = await action.getUserSettings();
    browser.test.assertTrue(
      userSettings.isOnToolbar,
      "isOnToolbar should be true after pinning"
    );

    await browser.test.notifyPass("getUserSettings");
  };

  tests[test]();
}'''


class BrowserActionGetUserSettingsTest(FirefoxTest):
    prefs = head.NOT_PINNED_BY_DEFAULT

    def run_extension(self, manifest_version, action, test):
        extension = self.load_extension(
            manifest={'manifest_version': manifest_version, **action},
            background=JS(BACKGROUND, json.dumps(test)))

        def pin(details):
            head.pin_to_toolbar(self, extension, details['shouldPinToToolbar'])
            extension.send_message(details['identifier'])
        extension.on_message('pinToToolbar', pin)
        extension.startup()
        extension.await_finish('getUserSettings')
        extension.unload()

    def test_01_browserAction_getUserSettings(self):
        self.run_extension(2, {'browser_action': {}}, 'getUserSettings')

    def test_02_action_getUserSettings(self):
        self.run_extension(3, {'action': {}}, 'getUserSettings')

    def test_03_browserAction_getUserSettings_default_area(self):
        for default_area in ['navbar', 'tabstrip', 'personaltoolbar']:
            self.run_extension(2, {'browser_action': {'default_area': default_area}},
                               'default_area_getUserSettings')

    def test_04_action_getUserSettings_default_area(self):
        for default_area in ['navbar', 'tabstrip', 'personaltoolbar']:
            self.run_extension(3, {'action': {'default_area': default_area}},
                               'default_area_getUserSettings')

    def test_05_browserAction_getUserSettings_menupanel_default_area(self):
        self.run_extension(2, {'browser_action': {'default_area': 'menupanel'}},
                           'menupanel_default_area_getUserSettings')

    def test_06_action_getUserSettings_menupanel_default_area(self):
        self.run_extension(3, {'action': {'default_area': 'menupanel'}},
                           'menupanel_default_area_getUserSettings')
