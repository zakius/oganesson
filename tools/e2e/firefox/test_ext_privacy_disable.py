"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_privacy_disable.js.

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

AddonManager's disable() and enable() are the user's, on chrome://extensions
(head.set_enabled()). The test's wait for network.http.speculative-parallel-limit
to change after a disable is the wait for management.setEnabled(), which
resolves once the browser has disabled the add-on and dropped its settings:
in this browser's form the pref doesn't always change (prediction on from the
add-on, then on from the user's setting). Its wait for Gecko's "ready" event
after an enable waits for the add-on's background to load again.

Left out: AddonTestUtils' start and stop of Gecko's add-on manager. The
add-ons' code is Firefox's, as it is."""

from extension_test_utils import JS, FirefoxTest
from firefox import head, head_privacy

OLD_ID = 'old_id@tests.mozilla.org'
NEW_ID = 'new_id@tests.mozilla.org'

# Create an object to hold the values to which we will initialize the prefs.
PREFS = {
    'network.prefetch-next': True,
    'network.http.speculative-parallel-limit': head_privacy.SPECULATIVE_PARALLEL_LIMIT,
    'network.dns.disablePrefetch': False,
}


class PrivacyDisableTest(FirefoxTest):
    # PREFS, in this browser's form.
    prefs = {
        'net': {'network_prediction_options': head_privacy.PREDICTION_STANDARD},
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        head_privacy.release_ubo_settings(cls.browser)

    def preference(self, name):
        return head_privacy.preference(self, name)

    def check_prefs(self, expected):
        for pref in PREFS:
            msg = f'{pref} set correctly.'
            expected_value = PREFS[pref] if expected else not PREFS[pref]
            if pref == 'network.http.speculative-parallel-limit':
                if expected:
                    expected_value = head_privacy.SPECULATIVE_PARALLEL_LIMIT
                else:
                    expected_value = 0
            self.is_(self.preference(pref), expected_value, msg)

    def enable(self, extension):
        """addon.enable(), and Gecko's "ready" event: the add-on's background
        loads again."""
        extension.ready = False
        head.set_enabled(self, extension, True)
        self.wait_reports(lambda: extension.ready, 'the background to load again')

    def test_01_disable(self):
        background = JS('''async function background() {
    browser.test.onMessage.addListener(async (msg, data) => {
      await browser.privacy.network.networkPredictionEnabled.set(data);
      let settingData =
        await browser.privacy.network.networkPredictionEnabled.get({});
      browser.test.sendMessage("privacyData", settingData);
    });
  }''')

        test_extensions = [
            self.load_extension(
                background=background,
                manifest={
                    'browser_specific_settings': {
                        'gecko': {
                            'id': OLD_ID,
                        },
                    },
                    'permissions': ['privacy'],
                },
                use_addon_manager='temporary'),

            self.load_extension(
                background=background,
                manifest={
                    'browser_specific_settings': {
                        'gecko': {
                            'id': NEW_ID,
                        },
                    },
                    'permissions': ['privacy'],
                },
                use_addon_manager='temporary'),
        ]

        for extension in test_extensions:
            extension.startup()

        # Set the value to true for the older extension.
        test_extensions[0].send_message('set', {'value': True})
        data = test_extensions[0].await_message('privacyData')
        self.check(data['value'], 'Value set to true for the older extension.')

        # Set the value to false for the newest extension.
        test_extensions[1].send_message('set', {'value': False})
        data = test_extensions[1].await_message('privacyData')
        self.check(not data['value'], 'Value set to false for the newest extension.')

        # Verify the prefs have been set to match the "false" setting.
        self.check_prefs(False)

        # Disable the newest extension.
        new_addon = test_extensions[1]
        head.set_enabled(self, new_addon, False)

        # Verify the prefs have been set to match the "true" setting.
        self.check_prefs(True)

        # Disable the older extension.
        old_addon = test_extensions[0]
        head.set_enabled(self, old_addon, False)

        # Verify the prefs have reverted back to their initial values.
        for pref in PREFS:
            self.is_(self.preference(pref), PREFS[pref], f'{pref} reset correctly.')

        # Re-enable the newest extension.
        self.enable(new_addon)

        # Verify the prefs have been set to match the "false" setting.
        self.check_prefs(False)

        # Re-enable the older extension.
        self.enable(old_addon)

        # Verify the prefs have remained set to match the "false" setting.
        self.check_prefs(False)

        for extension in test_extensions:
            extension.unload()
