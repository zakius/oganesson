"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_privacy.js.

Gecko's prefs that the test sets and reads take this browser's form
(head_privacy.py): each is read from this browser's own pref for its setting,
in the profile, and given in Firefox's form. Network prediction's three prefs
are net.network_prediction_options, browser.send_pings is enable_a_ping,
media.peerconnection.ice.* are webrtc.ip_handling_policy, media.peerconnection.enabled is always true,
signon.rememberSignons is credentials_enable_service,
network.http.sendRefererHeader is enable_referrers,
network.cookie.cookieBehavior is the cookies settings (third-party cookies
blocked, or all cookies blocked), privacy.globalprivacycontrol.enabled is
helium.global_privacy_control and dom.security.https_only_mode is
https_only_mode_enabled. The others have no setting here and read as None, so
their checks fail on the gap: privacy.resistFingerprinting,
privacy.trackingprotection.*, privacy.firstparty.isolate,
security.tls.version.* and dom.security.https_only_mode_pbm.

The class's `prefs` set the test's first values, as Firefox's test sets its
prefs: network prediction on, hyperlink auditing on, WebRTC's IP handling
policy "default", password saving on, referrers on and third-party cookies
allowed; the bundled uBlock Origin's settings that turn network prediction
and hyperlink auditing off are turned off first, as Firefox's test profile has
no other add-on. Firefox's other first values have no setting here. Gecko's
security.tls.version.min is Chromium's minimum, TLS 1.2 (3), so the test
takes its TLS 1.2 branch. Its default network.cookie.cookieBehavior is this
browser's default, third-party cookies blocked (1, "reject_third_party"). The
test's own Preferences.set() while the browser runs is the user's change in
Settings; one with no setting there fails the test.

Left out: AddonTestUtils' start and stop of Gecko's add-on manager, and its
overrideCertDB(). The add-ons' code is Firefox's, as it is."""

from extension_test_utils import JS, FirefoxTest
from firefox import head_privacy

READ_ONLY = True
TLS_MIN_PREF = head_privacy.TLS_MIN_PREF
TLS_MIN_VER = 'TLSv1.2'

BEHAVIORS = {
    head_privacy.BEHAVIOR_ACCEPT: 'allow_all',
    head_privacy.BEHAVIOR_REJECT_FOREIGN: 'reject_third_party',
    head_privacy.BEHAVIOR_REJECT: 'reject_all',
    head_privacy.BEHAVIOR_LIMIT_FOREIGN: 'allow_visited',
    head_privacy.BEHAVIOR_REJECT_TRACKER: 'reject_trackers',
    head_privacy.BEHAVIOR_PARTITION_FOREIGN: 'reject_trackers_and_partition_foreign',
}


class PrivacyTest(FirefoxTest):
    # Firefox's first values of the prefs of both tasks, in this browser's
    # form.
    prefs = {
        'net': {'network_prediction_options': head_privacy.PREDICTION_STANDARD},
        'enable_a_ping': True,
        'webrtc': {'ip_handling_policy': 'default'},
        'credentials_enable_service': True,
        'enable_referrers': True,
        'profile': {'cookie_controls_mode': head_privacy.COOKIES_ALLOW_THIRD_PARTY},
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        head_privacy.release_ubo_settings(cls.browser)

    def preference(self, name):
        return head_privacy.preference(self, name)

    def test_01_privacy(self):
        # Create an object to hold the values to which we will initialize the prefs.
        SETTINGS = {
            'network.networkPredictionEnabled': {
                'network.prefetch-next': True,
                # This pref starts with a numerical value and we need to use whatever the
                # default is or we encounter issues when the pref is reset during the test.
                'network.http.speculative-parallel-limit':
                    head_privacy.SPECULATIVE_PARALLEL_LIMIT,
                'network.dns.disablePrefetch': False,
            },
            'websites.hyperlinkAuditingEnabled': {
                'browser.send_pings': True,
            },
        }

        background = JS('''async function background() {
    browser.test.onMessage.addListener(async (msg, data, setting) => {
      // The second argument is the end of the api name,
      // e.g., "network.networkPredictionEnabled".
      let apiObj = setting.split(".").reduce((o, i) => o[i], browser.privacy);
      let settingData;
      switch (msg) {
        case "get":
          settingData = await apiObj.get(data);
          browser.test.sendMessage("gotData", settingData);
          break;

        case "set":
          await apiObj.set(data);
          settingData = await apiObj.get({});
          browser.test.sendMessage("afterSet", settingData);
          break;

        case "clear":
          await apiObj.clear(data);
          settingData = await apiObj.get({});
          browser.test.sendMessage("afterClear", settingData);
          break;
      }
    });
  }''')

        def load():
            return self.load_extension(
                background=background,
                manifest={
                    'permissions': ['privacy'],
                },
                use_addon_manager='temporary')

        # Create an array of extensions to install.
        test_extensions = [load(), load()]

        for extension in test_extensions:
            extension.startup()

        for setting in SETTINGS:
            test_extensions[0].send_message('get', {}, setting)
            data = test_extensions[0].await_message('gotData')
            self.check(data['value'], 'get returns expected value.')
            self.is_(data['levelOfControl'], 'controllable_by_this_extension',
                     'get returns expected levelOfControl.')

            test_extensions[0].send_message('get', {'incognito': True}, setting)
            data = test_extensions[0].await_message('gotData')
            self.check(data['value'], 'get returns expected value with incognito.')
            self.is_(data['levelOfControl'], 'not_controllable',
                     'get returns expected levelOfControl with incognito.')

            # Change the value to false.
            test_extensions[0].send_message('set', {'value': False}, setting)
            data = test_extensions[0].await_message('afterSet')
            self.check(not data['value'], 'get returns expected value after setting.')
            self.is_(data['levelOfControl'], 'controlled_by_this_extension',
                     'get returns expected levelOfControl after setting.')

            # Verify the prefs have been set to match the "false" setting.
            for pref in SETTINGS[setting]:
                msg = f'{pref} set correctly for {setting}'
                if pref == 'network.http.speculative-parallel-limit':
                    self.is_(self.preference(pref), 0, msg)
                else:
                    self.is_(self.preference(pref), not SETTINGS[setting][pref], msg)

            # Change the value with a newer extension.
            test_extensions[1].send_message('set', {'value': True}, setting)
            data = test_extensions[1].await_message('afterSet')
            self.check(data['value'],
                       'get returns expected value after setting via newer extension.')
            self.is_(data['levelOfControl'], 'controlled_by_this_extension',
                     'get returns expected levelOfControl after setting.')

            # Verify the prefs have been set to match the "true" setting.
            for pref in SETTINGS[setting]:
                msg = f'{pref} set correctly for {setting}'
                if pref == 'network.http.speculative-parallel-limit':
                    self.is_(self.preference(pref), head_privacy.SPECULATIVE_PARALLEL_LIMIT, msg)
                else:
                    self.is_(self.preference(pref), SETTINGS[setting][pref], msg)

            # Change the value with an older extension.
            test_extensions[0].send_message('set', {'value': False}, setting)
            data = test_extensions[0].await_message('afterSet')
            self.check(data['value'], 'Newer extension remains in control.')
            self.is_(data['levelOfControl'], 'controlled_by_other_extensions',
                     'get returns expected levelOfControl when controlled by other.')

            # Clear the value of the newer extension.
            test_extensions[1].send_message('clear', {}, setting)
            data = test_extensions[1].await_message('afterClear')
            self.check(not data['value'], 'Older extension gains control.')
            self.is_(data['levelOfControl'], 'controllable_by_this_extension',
                     'Expected levelOfControl returned after clearing.')

            test_extensions[0].send_message('get', {}, setting)
            data = test_extensions[0].await_message('gotData')
            self.check(not data['value'], 'Current, older extension has control.')
            self.is_(data['levelOfControl'], 'controlled_by_this_extension',
                     'Expected levelOfControl returned after clearing.')

            # Set the value again with the newer extension.
            test_extensions[1].send_message('set', {'value': True}, setting)
            data = test_extensions[1].await_message('afterSet')
            self.check(data['value'],
                       'get returns expected value after setting via newer extension.')
            self.is_(data['levelOfControl'], 'controlled_by_this_extension',
                     'get returns expected levelOfControl after setting.')

            # Unload the newer extension. Expect the older extension to regain control.
            test_extensions[1].unload()
            test_extensions[0].send_message('get', {}, setting)
            data = test_extensions[0].await_message('gotData')
            self.check(not data['value'], 'Older extension regained control.')
            self.is_(data['levelOfControl'], 'controlled_by_this_extension',
                     'Expected levelOfControl returned after unloading.')

            # Reload the extension for the next iteration of the loop.
            test_extensions[1] = load()
            test_extensions[1].startup()

            # Clear the value of the older extension.
            test_extensions[0].send_message('clear', {}, setting)
            data = test_extensions[0].await_message('afterClear')
            self.check(data['value'], 'Setting returns to original value when all are cleared.')
            self.is_(data['levelOfControl'], 'controllable_by_this_extension',
                     'Expected levelOfControl returned after clearing.')

            # Verify that our initial values were restored.
            for pref in SETTINGS[setting]:
                self.is_(self.preference(pref), SETTINGS[setting][pref],
                         f'{pref} was reset to its initial value.')

        for extension in test_extensions:
            extension.unload()

    def test_02_privacy_other_prefs(self):
        default_cookie_behavior = head_privacy.DEFAULT_COOKIE_BEHAVIOR
        default_behavior = BEHAVIORS[default_cookie_behavior]

        extension = self.load_extension(
            background=JS('''async function background() {
    let listeners = new Set([]);
    browser.test.onMessage.addListener(async (msg, data, setting, readOnly) => {
      // The second argument is the end of the api name,
      // e.g., "network.webRTCIPHandlingPolicy".
      let apiObj = setting.split(".").reduce((o, i) => o[i], browser.privacy);
      if (msg == "get") {
        browser.test.sendMessage("gettingData", await apiObj.get({}));
        return;
      }

      // Don't add more than one listener per apiName.  We leave the
      // listener to ensure we do not get more calls than we expect.
      if (!listeners.has(setting)) {
        apiObj.onChange.addListener(details => {
          browser.test.sendMessage("settingData", details);
        });
        listeners.add(setting);
      }
      try {
        await apiObj.set(data);
      } catch (e) {
        browser.test.sendMessage("settingThrowsException", {
          message: e.message,
        });
      }
      // Readonly settings will not trigger onChange, return the setting now.
      if (readOnly) {
        browser.test.sendMessage("settingData", await apiObj.get({}));
      }
    });
  }'''),
            manifest={
                'permissions': ['privacy'],
            },
            use_addon_manager='temporary')

        extension.startup()

        def test_setting(setting, value, expected, expected_value=None):
            if expected_value is None:
                expected_value = value
            extension.send_message('set', {'value': value}, setting)
            data = extension.await_message('settingData')
            self.is_(data['value'], expected_value,
                     f'Got expected result on setting {setting} to {value!r}')
            for pref in expected:
                self.is_(self.preference(pref), expected[pref],
                         f'{pref} set correctly for {expected[pref]}')

        def test_setting_exception(setting, value, expected):
            extension.send_message('set', {'value': value}, setting)
            data = extension.await_message('settingThrowsException')
            self.is_(data['message'], expected, f'{setting} set to {value!r} throws')

        def test_getting(getting, expected, expected_value):
            extension.send_message('get', None, getting)
            data = extension.await_message('gettingData')
            self.is_(data['value'], expected_value, f'Got expected result on getting {getting}')
            for pref in expected:
                self.is_(self.preference(pref), expected[pref],
                         f'{pref} get correctly for {expected[pref]}')

        test_setting(
            'network.webRTCIPHandlingPolicy',
            'default_public_and_private_interfaces',
            {
                'media.peerconnection.ice.default_address_only': True,
                'media.peerconnection.ice.no_host': False,
                'media.peerconnection.ice.proxy_only_if_behind_proxy': False,
                'media.peerconnection.ice.proxy_only': False,
            })
        test_setting(
            'network.webRTCIPHandlingPolicy',
            'default_public_interface_only',
            {
                'media.peerconnection.ice.default_address_only': True,
                'media.peerconnection.ice.no_host': True,
                'media.peerconnection.ice.proxy_only_if_behind_proxy': False,
                'media.peerconnection.ice.proxy_only': False,
            })
        test_setting(
            'network.webRTCIPHandlingPolicy',
            'disable_non_proxied_udp',
            {
                'media.peerconnection.ice.default_address_only': True,
                'media.peerconnection.ice.no_host': True,
                'media.peerconnection.ice.proxy_only_if_behind_proxy': True,
                'media.peerconnection.ice.proxy_only': False,
            })
        test_setting('network.webRTCIPHandlingPolicy', 'proxy_only', {
            'media.peerconnection.ice.default_address_only': False,
            'media.peerconnection.ice.no_host': False,
            'media.peerconnection.ice.proxy_only_if_behind_proxy': False,
            'media.peerconnection.ice.proxy_only': True,
        })
        test_setting('network.webRTCIPHandlingPolicy', 'default', {
            'media.peerconnection.ice.default_address_only': False,
            'media.peerconnection.ice.no_host': False,
            'media.peerconnection.ice.proxy_only_if_behind_proxy': False,
            'media.peerconnection.ice.proxy_only': False,
        })

        test_setting('network.peerConnectionEnabled', False, {
            'media.peerconnection.enabled': False,
        })
        test_setting('network.peerConnectionEnabled', True, {
            'media.peerconnection.enabled': True,
        })

        test_setting('websites.referrersEnabled', False, {
            'network.http.sendRefererHeader': 0,
        })
        test_setting('websites.referrersEnabled', True, {
            'network.http.sendRefererHeader': 2,
        })

        test_setting('websites.resistFingerprinting', False, {
            'privacy.resistFingerprinting': False,
        })
        test_setting('websites.resistFingerprinting', True, {
            'privacy.resistFingerprinting': True,
        })

        test_setting('websites.trackingProtectionMode', 'always', {
            'privacy.trackingprotection.enabled': True,
            'privacy.trackingprotection.pbmode.enabled': True,
        })
        test_setting('websites.trackingProtectionMode', 'never', {
            'privacy.trackingprotection.enabled': False,
            'privacy.trackingprotection.pbmode.enabled': False,
        })
        test_setting('websites.trackingProtectionMode', 'private_browsing', {
            'privacy.trackingprotection.enabled': False,
            'privacy.trackingprotection.pbmode.enabled': True,
        })

        test_setting('services.passwordSavingEnabled', False, {
            'signon.rememberSignons': False,
        })
        test_setting('services.passwordSavingEnabled', True, {
            'signon.rememberSignons': True,
        })

        test_setting(
            'websites.cookieConfig',
            {'behavior': 'reject_third_party', 'nonPersistentCookies': True},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_REJECT_FOREIGN,
            },
            {'behavior': 'reject_third_party', 'nonPersistentCookies': False})
        # A missing nonPersistentCookies property should default to false.
        test_setting(
            'websites.cookieConfig',
            {'behavior': 'reject_third_party'},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_REJECT_FOREIGN,
            },
            {'behavior': 'reject_third_party', 'nonPersistentCookies': False})
        # A missing behavior property should reset the pref.
        test_setting(
            'websites.cookieConfig',
            {'nonPersistentCookies': True},
            {
                'network.cookie.cookieBehavior': default_cookie_behavior,
            },
            {'behavior': default_behavior, 'nonPersistentCookies': False})
        test_setting(
            'websites.cookieConfig',
            {'behavior': 'reject_all'},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_REJECT,
            },
            {'behavior': 'reject_all', 'nonPersistentCookies': False})
        test_setting(
            'websites.cookieConfig',
            {'behavior': 'allow_visited'},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_LIMIT_FOREIGN,
            },
            {'behavior': 'allow_visited', 'nonPersistentCookies': False})
        test_setting(
            'websites.cookieConfig',
            {'behavior': 'allow_all'},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_ACCEPT,
            },
            {'behavior': 'allow_all', 'nonPersistentCookies': False})
        test_setting(
            'websites.cookieConfig',
            {'nonPersistentCookies': True},
            {
                'network.cookie.cookieBehavior': default_cookie_behavior,
            },
            {'behavior': default_behavior, 'nonPersistentCookies': False})
        test_setting(
            'websites.cookieConfig',
            {'nonPersistentCookies': False},
            {
                'network.cookie.cookieBehavior': default_cookie_behavior,
            },
            {'behavior': default_behavior, 'nonPersistentCookies': False})
        test_setting(
            'websites.cookieConfig',
            {'behavior': 'reject_trackers'},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_REJECT_TRACKER,
            },
            {'behavior': 'reject_trackers', 'nonPersistentCookies': False})
        test_setting(
            'websites.cookieConfig',
            {'behavior': 'reject_trackers_and_partition_foreign'},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_PARTITION_FOREIGN,
            },
            {
                'behavior': 'reject_trackers_and_partition_foreign',
                'nonPersistentCookies': False,
            })

        # 1. Can't enable FPI when cookie behavior is "reject_trackers_and_partition_foreign"
        test_setting_exception(
            'websites.firstPartyIsolate',
            True,
            "Can't enable firstPartyIsolate when cookieBehavior is "
            "'reject_trackers_and_partition_foreign'")

        # 2. Change cookieConfig to reject_trackers should work normally.
        test_setting(
            'websites.cookieConfig',
            {'behavior': 'reject_trackers'},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_REJECT_TRACKER,
            },
            {'behavior': 'reject_trackers', 'nonPersistentCookies': False})

        # 3. Enable FPI
        test_setting('websites.firstPartyIsolate', True, {
            'privacy.firstparty.isolate': True,
        })

        # 4. When FPI is enabled, change setting to "reject_trackers_and_partition_foreign" is invalid
        test_setting_exception(
            'websites.cookieConfig',
            {'behavior': 'reject_trackers_and_partition_foreign'},
            "Invalid cookieConfig 'reject_trackers_and_partition_foreign' when "
            'firstPartyIsolate is enabled')

        # 5. Set conflict settings manually and check prefs.
        head_privacy.set_preference(self, 'network.cookie.cookieBehavior', 5)
        test_getting(
            'websites.firstPartyIsolate',
            {'privacy.firstparty.isolate': True},
            True)
        test_getting(
            'websites.cookieConfig',
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_PARTITION_FOREIGN,
            },
            {
                'behavior': 'reject_trackers_and_partition_foreign',
                'nonPersistentCookies': False,
            })

        # 6. It is okay to set current saved value.
        test_setting('websites.firstPartyIsolate', True, {
            'privacy.firstparty.isolate': True,
        })
        test_setting(
            'websites.cookieConfig',
            {'behavior': 'reject_trackers_and_partition_foreign'},
            {
                'network.cookie.cookieBehavior': head_privacy.BEHAVIOR_PARTITION_FOREIGN,
            },
            {
                'behavior': 'reject_trackers_and_partition_foreign',
                'nonPersistentCookies': False,
            })

        test_setting('websites.firstPartyIsolate', False, {
            'privacy.firstparty.isolate': False,
        })

        test_setting(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.2',
                'maximum': 'TLSv1.3',
            },
            {
                'security.tls.version.min': 3,
                'security.tls.version.max': 4,
            })

        # Single values
        test_setting(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.3',
            },
            {
                'security.tls.version.min': 4,
                'security.tls.version.max': 4,
            },
            {
                'minimum': 'TLSv1.3',
                'maximum': 'TLSv1.3',
            })

        # Single values
        test_setting(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.3',
            },
            {
                'security.tls.version.min': 4,
                'security.tls.version.max': 4,
            },
            {
                'minimum': 'TLSv1.3',
                'maximum': 'TLSv1.3',
            })

        # Invalid values.
        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'minimum': 'invalid',
                'maximum': 'invalid',
            },
            'Setting TLS version invalid is not allowed for security reasons.')

        # Invalid values.
        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'minimum': 'invalid2',
            },
            'Setting TLS version invalid2 is not allowed for security reasons.')

        # Invalid values.
        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'maximum': 'invalid3',
            },
            'Setting TLS version invalid3 is not allowed for security reasons.')

        test_setting(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.2',
            },
            {
                'security.tls.version.min': 3,
                'security.tls.version.max': 4,
            },
            {
                'minimum': 'TLSv1.2',
                'maximum': 'TLSv1.3',
            })

        test_setting(
            'network.tlsVersionRestriction',
            {
                'maximum': 'TLSv1.2',
            },
            {
                'security.tls.version.min': TLS_MIN_PREF,
                'security.tls.version.max': 3,
            },
            {
                'minimum': TLS_MIN_VER,
                'maximum': 'TLSv1.2',
            })

        # Not supported version: Firefox's branch for a minimum of TLS 1.2.
        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1',
            },
            'Setting TLS version TLSv1 is not allowed for security reasons.')

        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.1',
            },
            'Setting TLS version TLSv1.1 is not allowed for security reasons.')

        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'maximum': 'TLSv1',
            },
            'Setting TLS version TLSv1 is not allowed for security reasons.')

        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'maximum': 'TLSv1.1',
            },
            'Setting TLS version TLSv1.1 is not allowed for security reasons.')

        # Min vs Max
        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.3',
                'maximum': 'TLSv1.2',
            },
            'Setting TLS min version grater than the max version is not allowed.')

        # Min vs Max (with default max)
        test_setting(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.2',
                'maximum': 'TLSv1.2',
            },
            {
                'security.tls.version.min': 3,
                'security.tls.version.max': 3,
            })
        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.3',
            },
            'Setting TLS min version grater than the max version is not allowed.')

        # Max vs Min
        test_setting(
            'network.tlsVersionRestriction',
            {
                'minimum': 'TLSv1.3',
                'maximum': 'TLSv1.3',
            },
            {
                'security.tls.version.min': 4,
                'security.tls.version.max': 4,
            })
        test_setting_exception(
            'network.tlsVersionRestriction',
            {
                'maximum': 'TLSv1.2',
            },
            'Setting TLS max version lower than the min version is not allowed.')

        # Empty value.
        test_setting(
            'network.tlsVersionRestriction',
            {},
            {
                'security.tls.version.min': TLS_MIN_PREF,
                'security.tls.version.max': 4,
            },
            {
                'minimum': TLS_MIN_VER,
                'maximum': 'TLSv1.3',
            })

        GLOBAL_PRIVACY_CONTROL_PREF_NAME = 'privacy.globalprivacycontrol.enabled'

        head_privacy.set_preference(self, GLOBAL_PRIVACY_CONTROL_PREF_NAME, False)
        test_getting('network.globalPrivacyControl', {}, False)

        head_privacy.set_preference(self, GLOBAL_PRIVACY_CONTROL_PREF_NAME, True)
        test_getting('network.globalPrivacyControl', {}, True)

        # trying to "set" should have no effect when readonly!
        extension.send_message(
            'set',
            {'value': not self.preference(GLOBAL_PRIVACY_CONTROL_PREF_NAME)},
            'network.globalPrivacyControl',
            READ_ONLY)
        read_only_gpc_data = extension.await_message('settingData')
        self.is_(read_only_gpc_data['value'], self.preference(GLOBAL_PRIVACY_CONTROL_PREF_NAME),
                 'extension cannot set globalPrivacyControl')

        self.is_(self.preference(GLOBAL_PRIVACY_CONTROL_PREF_NAME), True,
                 f'{GLOBAL_PRIVACY_CONTROL_PREF_NAME} is unchanged')

        HTTPS_ONLY_PREF_NAME = 'dom.security.https_only_mode'
        HTTPS_ONLY_PBM_PREF_NAME = 'dom.security.https_only_mode_pbm'

        head_privacy.set_preference(self, HTTPS_ONLY_PREF_NAME, False)
        head_privacy.set_preference(self, HTTPS_ONLY_PBM_PREF_NAME, False)
        test_getting('network.httpsOnlyMode', {}, 'never')

        head_privacy.set_preference(self, HTTPS_ONLY_PREF_NAME, True)
        head_privacy.set_preference(self, HTTPS_ONLY_PBM_PREF_NAME, False)
        test_getting('network.httpsOnlyMode', {}, 'always')

        head_privacy.set_preference(self, HTTPS_ONLY_PREF_NAME, False)
        head_privacy.set_preference(self, HTTPS_ONLY_PBM_PREF_NAME, True)
        test_getting('network.httpsOnlyMode', {}, 'private_browsing')

        # Please note that if https_only_mode = true, then
        # https_only_mode_pbm has no effect.
        head_privacy.set_preference(self, HTTPS_ONLY_PREF_NAME, True)
        head_privacy.set_preference(self, HTTPS_ONLY_PBM_PREF_NAME, True)
        test_getting('network.httpsOnlyMode', {}, 'always')

        # trying to "set" should have no effect when readonly!
        extension.send_message(
            'set',
            {'value': 'never'},
            'network.httpsOnlyMode',
            READ_ONLY)
        read_only_data = extension.await_message('settingData')
        self.is_(read_only_data['value'], 'always', 'extension cannot set httpsOnlyMode')

        self.is_(self.preference(HTTPS_ONLY_PREF_NAME), True, f'{HTTPS_ONLY_PREF_NAME} is unchanged')
        self.is_(self.preference(HTTPS_ONLY_PBM_PREF_NAME), True,
                 f'{HTTPS_ONLY_PBM_PREF_NAME} is unchanged')

        extension.unload()

    def test_03_exceptions(self):
        extension = self.load_extension(
            background=JS('''async function background() {
    await browser.test.assertRejects(
      browser.privacy.network.networkPredictionEnabled.set({
        value: true,
        scope: "regular_only",
      }),
      "Firefox does not support the regular_only settings scope.",
      "Expected rejection calling set with invalid scope."
    );

    await browser.test.assertRejects(
      browser.privacy.network.networkPredictionEnabled.clear({
        scope: "incognito_persistent",
      }),
      "Firefox does not support the incognito_persistent settings scope.",
      "Expected rejection calling clear with invalid scope."
    );

    browser.test.notifyPass("exceptionTests");
  }'''),
            manifest={
                'permissions': ['privacy'],
            })

        extension.startup()
        extension.await_finish('exceptionTests')
        extension.unload()
