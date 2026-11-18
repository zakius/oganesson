"""Gecko's prefs behind Firefox's privacy settings, in this browser's form, for
the ports of Firefox's privacy tests. Firefox's tests set and read Gecko's
prefs (Preferences.set() and get()); here each is read from this browser's
own pref for that setting, in the profile (chrome://prefs-internals), and
given in Firefox's form:

- network.prefetch-next, network.dns.disablePrefetch and
  network.http.speculative-parallel-limit (networkPredictionEnabled):
  Chromium's net.network_prediction_options, on unless 2 (disabled). Chromium
  has no number of speculative connections: on reads as Firefox's default, 6,
  and off as 0.
- browser.send_pings (hyperlinkAuditingEnabled): enable_a_ping.
- media.peerconnection.ice.* (webRTCIPHandlingPolicy): Chromium's
  webrtc.ip_handling_policy, whose values are Firefox's but for proxy_only,
  which Chromium doesn't have: ice.proxy_only is always false.
- media.peerconnection.enabled (peerConnectionEnabled): always true, as WebRTC
  is always on here (zakius/dubna#93).
- signon.rememberSignons (passwordSavingEnabled): credentials_enable_service.
- network.http.sendRefererHeader (referrersEnabled): enable_referrers, 2 when
  on and 0 when off.
- network.cookie.cookieBehavior (cookieConfig): cookies blocked in Settings
  (profile.default_content_setting_values.cookies) are 2 (reject all), and
  third-party cookies blocked (profile.cookie_controls_mode 1) are 1 (reject
  third-party); 0 (accept) otherwise. Firefox's 3, 4 and 5 (visited, trackers,
  trackers and partitioned) have no equal.
- privacy.globalprivacycontrol.enabled (globalPrivacyControl): Helium's
  helium.global_privacy_control.
- dom.security.https_only_mode (httpsOnlyMode): https_only_mode_enabled,
  "Always use secure connections".

The others have no setting in this browser, and read as None, so that a check
of them fails on the gap: privacy.resistFingerprinting,
privacy.trackingprotection.enabled and .pbmode.enabled,
privacy.firstparty.isolate, security.tls.version.min and .max (Chromium's
minimum TLS version is only a policy), and dom.security.https_only_mode_pbm
(this browser has no separate setting for private windows).

The test's own Preferences.set() of a pref while the browser runs is the
user's change in Settings (settingsPrivate), for the prefs above that Settings
has; one without a setting there fails the test.

The bundled uBlock Origin turns network prediction and hyperlink auditing off
by default, as an add-on that controls both settings. Firefox's test profile
has no other add-on: release_ubo_settings() turns those two settings of
uBlock's off, as the user can, and uBlock clears its values."""

from firefox import head_containers
from harness import wait_for

# Chromium's NetworkPredictionOptions (net.network_prediction_options).
PREDICTION_STANDARD = 0
PREDICTION_DISABLED = 2
# Firefox's default network.http.speculative-parallel-limit, which
# ExtensionPreferencesManager.getDefaultValue() gives.
SPECULATIVE_PARALLEL_LIMIT = 6
# Chromium's CookieControlsMode (profile.cookie_controls_mode).
COOKIES_ALLOW_THIRD_PARTY = 0
COOKIES_BLOCK_THIRD_PARTY = 1
# Chromium's ContentSetting.
CONTENT_SETTING_BLOCK = 2
# Firefox's nsICookieService behaviors (network.cookie.cookieBehavior).
BEHAVIOR_ACCEPT = 0
BEHAVIOR_REJECT_FOREIGN = 1
BEHAVIOR_REJECT = 2
BEHAVIOR_LIMIT_FOREIGN = 3
BEHAVIOR_REJECT_TRACKER = 4
BEHAVIOR_PARTITION_FOREIGN = 5
# This browser's default, third-party cookies blocked, in Firefox's form.
DEFAULT_COOKIE_BEHAVIOR = BEHAVIOR_REJECT_FOREIGN
# Chromium's minimum TLS version, 1.2, as Firefox's security.tls.version.min.
TLS_MIN_PREF = 3


def prediction_on(prefs):
    return prefs['net']['network_prediction_options']['value'] != PREDICTION_DISABLED


def speculative_parallel_limit(prefs):
    if prediction_on(prefs):
        return SPECULATIVE_PARALLEL_LIMIT
    return 0


def webrtc_policy(prefs):
    return prefs['webrtc']['ip_handling_policy']['value']


def cookie_behavior(prefs):
    cookies = prefs['profile']['default_content_setting_values'].get('cookies')
    if cookies and cookies['value'] == CONTENT_SETTING_BLOCK:
        return BEHAVIOR_REJECT
    if prefs['profile']['cookie_controls_mode']['value'] == COOKIES_BLOCK_THIRD_PARTY:
        return BEHAVIOR_REJECT_FOREIGN
    return BEHAVIOR_ACCEPT


# Each Gecko pref that has an equal here: its value in Firefox's form, from
# the profile's prefs.
FIREFOX_PREFS = {
    'network.prefetch-next': prediction_on,
    'network.http.speculative-parallel-limit': speculative_parallel_limit,
    'network.dns.disablePrefetch': lambda prefs: not prediction_on(prefs),
    'browser.send_pings': lambda prefs: prefs['enable_a_ping']['value'],
    'media.peerconnection.ice.default_address_only':
        lambda prefs: webrtc_policy(prefs) != 'default',
    'media.peerconnection.ice.no_host': lambda prefs: webrtc_policy(prefs) in (
        'default_public_interface_only', 'disable_non_proxied_udp'),
    'media.peerconnection.ice.proxy_only_if_behind_proxy':
        lambda prefs: webrtc_policy(prefs) == 'disable_non_proxied_udp',
    'media.peerconnection.ice.proxy_only': lambda prefs: False,
    'media.peerconnection.enabled': lambda prefs: True,
    'signon.rememberSignons': lambda prefs: prefs['credentials_enable_service']['value'],
    'network.http.sendRefererHeader':
        lambda prefs: 2 if prefs['enable_referrers']['value'] else 0,
    'network.cookie.cookieBehavior': cookie_behavior,
    'privacy.globalprivacycontrol.enabled':
        lambda prefs: prefs['helium']['global_privacy_control']['value'],
    'dom.security.https_only_mode': lambda prefs: prefs['https_only_mode_enabled']['value'],
}

# The Settings pref and its value for each value of a Gecko pref that the
# test sets while the browser runs.
SETTINGS_PREFS = {
    'privacy.globalprivacycontrol.enabled': {
        False: ('helium.global_privacy_control', False),
        True: ('helium.global_privacy_control', True),
    },
    'dom.security.https_only_mode': {
        False: ('https_only_mode_enabled', False),
        True: ('https_only_mode_enabled', True),
    },
    'network.cookie.cookieBehavior': {
        BEHAVIOR_ACCEPT: ('profile.cookie_controls_mode', COOKIES_ALLOW_THIRD_PARTY),
        BEHAVIOR_REJECT_FOREIGN: ('profile.cookie_controls_mode', COOKIES_BLOCK_THIRD_PARTY),
    },
}


def preference(test, name):
    """Preferences.get(name): None for a pref with no setting here."""
    if name not in FIREFOX_PREFS:
        return None
    return FIREFOX_PREFS[name](test.browser.profile_prefs())


def set_preference(test, name, value):
    """Preferences.set(name, value): the user's change in Settings."""
    if value not in SETTINGS_PREFS.get(name, {}):
        raise AssertionError(f'Preferences.set({name}, {value}): no such setting in this browser')
    pref, pref_value = SETTINGS_PREFS[name][value]
    head_containers.set_pref(test, pref, pref_value)


def release_ubo_settings(browser):
    """uBlock Origin's "Disable pre-fetching" and "Disable hyperlink
    auditing" off: it no longer controls the two settings."""
    ubo = browser.ubo_background()
    try:
        ubo.eval('µBlock.changeUserSettings("prefetchingDisabled", false), '
                 'µBlock.changeUserSettings("hyperlinkAuditingDisabled", false), 0',
                 gesture=False)
    finally:
        ubo.close()

    def released():
        prefs = browser.profile_prefs()
        prediction = prefs['net']['network_prediction_options'].get('metadata', [])
        pings = prefs['enable_a_ping'].get('metadata', [])
        return 'extension_controlled' not in prediction + pings
    wait_for(released, what='uBlock Origin to clear its settings')
