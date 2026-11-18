"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_privacy_update.js.

Gecko's network prediction prefs take this browser's form (head_privacy.py):
network.prefetch-next, network.dns.disablePrefetch and
network.http.speculative-parallel-limit read Chromium's
net.network_prediction_options. The class's `prefs` set the test's first
values: network prediction on. Chromium has no number of speculative
connections, so Firefox's first value of network.http.speculative-parallel-limit,
10, is its default here: on reads as Firefox's default, 6.
The bundled uBlock Origin's "Disable pre-fetching" is turned off first, so
that it no longer controls the setting, as Firefox's test profile has no
other add-on.

Gecko's add-on manager checks for the update (promiseFindAddonUpdates()) and
installs it (promiseCompleteAllInstalls()); here the user checks for updates
on chrome://extensions, and extension.awaitStartup() waits for the add-on to
run as 2.0. The add-on loaded with use_addon_manager='permanent' is unpacked,
which Chromium never updates. extension.version is the add-on's version that
chrome://extensions gives. The test's server, localhost in Firefox, is
example.com here, as in the browserSettings port; it takes the 2.0 .xpi as
Firefox's test registers it, with the test's own add-on token in it, so that
the 2.0 add-on's reports count.

Left out: AddonTestUtils' start and stop of Gecko's add-on manager, its
overrideCertDB(), and extensions.checkUpdateSecurity, a Gecko pref that lets
an update come over HTTP: this browser has no such check. The add-ons' code
is Firefox's, as it is."""

import io
import json
import zipfile

from extension_test_utils import JS, TEST_API, TEST_API_FILE, FirefoxTest, generate_files
from firefox import head_privacy
from harness import wait_for

EXTENSION_ID = 'test_privacy_addon_update@tests.mozilla.org'

# Create a object to hold the values to which we will initialize the prefs.
PREFS = {
    'network.prefetch-next': True,
    'network.http.speculative-parallel-limit': head_privacy.SPECULATIVE_PARALLEL_LIMIT,
    'network.dns.disablePrefetch': False,
}

BACKGROUND = JS('''async function background() {
    browser.test.onMessage.addListener(async (msg, data) => {
      let settingData;
      switch (msg) {
        case "get":
          settingData =
            await browser.privacy.network.networkPredictionEnabled.get({});
          browser.test.sendMessage("privacyData", settingData);
          break;

        case "set":
          await browser.privacy.network.networkPredictionEnabled.set(data);
          settingData =
            await browser.privacy.network.networkPredictionEnabled.get({});
          browser.test.sendMessage("privacyData", settingData);
          break;
      }
    });
  }''')


def xpi(files):
    """A .xpi of these files."""
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return data.getvalue()


class PrivacyUpdateTest(FirefoxTest):
    # PREFS, in this browser's form.
    prefs = {
        'net': {'network_prediction_options': head_privacy.PREDICTION_STANDARD},
    }
    hosts = ('example.com',)
    routes = {
        '/test_update.json': (200, {'Content-Type': 'application/json'}, json.dumps({
            'addons': {
                EXTENSION_ID: {
                    'updates': [
                        {
                            'version': '2.0',
                            'update_link': 'http://example.com/addons/test_privacy-2.0.xpi',
                        },
                    ],
                },
            },
        }).encode()),
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        head_privacy.release_ubo_settings(cls.browser)

    def addon_version(self, extension):
        """extension.version: the add-on's version on chrome://extensions."""
        page = self.open_tab('chrome://extensions')
        try:
            wait_for(lambda: page.eval('!!chrome.management'), what='chrome://extensions')
            return page.eval(f'chrome.management.get({json.dumps(extension.id)})'
                             '.then(e => e.version)')
        finally:
            self.browser.close_target(page)

    def test_01_privacy_update(self):
        extension = self.load_extension(
            use_addon_manager='permanent',
            manifest={
                'version': '1.0',
                'browser_specific_settings': {
                    'gecko': {
                        'id': EXTENSION_ID,
                        'update_url': 'http://example.com/test_update.json',
                    },
                },
                'permissions': ['privacy'],
            },
            background=BACKGROUND)

        # createTempWebExtensionFile(), and the server's registerFile().
        files = generate_files({
            'version': '2.0',
            'browser_specific_settings': {
                'gecko': {
                    'id': EXTENSION_ID,
                },
            },
            'permissions': ['privacy'],
        }, BACKGROUND, None)
        files[TEST_API_FILE] = TEST_API.replace('%TOKEN%', extension.token)
        self.server.routes['/addons/test_privacy-2.0.xpi'] = (
            200, {'Content-Type': 'application/x-xpinstall'}, xpi(files))

        extension.startup()

        # Change the value to false.
        extension.send_message('set', {'value': False})
        data = extension.await_message('privacyData')
        self.check(not data['value'], 'get returns expected value after setting.')

        self.is_(self.addon_version(extension), '1.0',
                 'The installed addon has the expected version.')

        # The user checks for updates.
        page = self.open_tab('chrome://extensions')
        try:
            wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
            page.eval('chrome.developerPrivate.autoUpdate()')
        finally:
            self.browser.close_target(page)

        # extension.awaitStartup()
        wait_for(lambda: self.addon_version(extension) == '2.0', what='the update to start')

        self.is_(self.addon_version(extension), '2.0',
                 'The updated addon has the expected version.')

        extension.send_message('get')
        data = extension.await_message('privacyData')
        self.check(not data['value'], 'get returns expected value after updating.')

        # Verify the prefs are still set to match the "false" setting.
        for pref in PREFS:
            msg = f'{pref} set correctly.'
            if pref == 'network.http.speculative-parallel-limit':
                expected_value = 0
            else:
                expected_value = not PREFS[pref]
            self.is_(head_privacy.preference(self, pref), expected_value, msg)

        extension.unload()
