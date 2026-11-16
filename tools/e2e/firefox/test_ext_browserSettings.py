"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_browserSettings.js.

After each set(), Firefox's test reads Gecko's prefs. Here those that have an
equal in this browser are read from its profile prefs (chrome://prefs-internals)
and given in Firefox's form (FIREFOX_PREFS); the class's `prefs` set them first,
as Firefox's test sets its prefs. The checks of the others are left out, since
this browser has no such setting: the cache (browser.cache.*), the events that
may open pop-ups (dom.popup_allowed_events), when the context menu opens
(ui.context_menus.after_mouseup), double-click to close a tab, opening
bookmarks, searches and address bar results in new tabs, the content colour
scheme, document fonts, zoom, colour management and vertical tabs. Left out
too: AddonTestUtils' start and stop of Gecko's add-on manager.

In delay_updates_settings_after_restart, Gecko's add-on manager checks for the
update (promiseFindAddonUpdates()) and installs it, which the update waits
for (STATE_POSTPONED, a Gecko internal, left out); here the user checks for
updates on chrome://extensions. The add-on loaded with
use_addon_manager='permanent' is unpacked, which Chromium never updates.
The add-ons' code is Firefox's, as it is."""

import io
import json
import zipfile

from extension_test_utils import JS, FirefoxTest
from harness import wait_for

SETTINGS_ID = 'test_settings_staged_restart_webext@tests.mozilla.org'

# Firefox's Services.perms actions.
PERM_UNKNOWN_ACTION = 0
PERM_DENY_ACTION = 2
# Chromium's ContentSetting.
CONTENT_SETTING_BLOCK = 2


def document_color_use(prefs):
    """browser.display.document_color_use from this browser's page colors,
    as firefox_browser_settings.cc reads them: 0 high contrast only, 1 never,
    2 always."""
    a11y = prefs['settings']['a11y']
    requested = a11y['requested_page_colors']['value']
    if requested == 1:  # PageColors::kOff
        return 1
    if requested == 0 or a11y['apply_page_colors_only_on_increased_contrast']['value']:
        return 0
    return 2


# Firefox's prefs that this browser has an equal of: each reads the profile's
# prefs and gives the value in Firefox's form.
FIREFOX_PREFS = {
    'image.animation_mode': lambda prefs: {'allowed': 'normal'}.get(
        prefs['settings']['a11y']['animation_policy']['value'],
        prefs['settings']['a11y']['animation_policy']['value']),
    'permissions.default.desktop-notification': lambda prefs: (
        PERM_DENY_ACTION
        if prefs['profile']['default_content_setting_values']['notifications']['value']
        == CONTENT_SETTING_BLOCK else PERM_UNKNOWN_ACTION),
    # oganesson's tab behavior (docs/tab-behavior.md): links at the end
    # (2) are insertRelatedAfterCurrent false.
    'browser.tabs.insertRelatedAfterCurrent':
        lambda prefs: prefs['oganesson']['tabs']['link_position']['value'] != 2,
    'browser.tabs.insertAfterCurrent':
        lambda prefs: prefs['helium']['browser']['new_tab_next_to_active']['value'],
    'browser.display.document_color_use': document_color_use,
}


def xpi(manifest):
    """AddonTestUtils.createTempXPIFile(): a .xpi with this manifest."""
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
    return data.getvalue()


UPDATE_XPI = xpi({
    'manifest_version': 2,
    'name': 'Delay Upgrade',
    'version': '2.0',
    'browser_specific_settings': {
        'gecko': {'id': SETTINGS_ID},
    },
    'permissions': ['browserSettings'],
})


class BrowserSettingsTest(FirefoxTest):
    # Firefox's PREFS, in this browser's form: animations off, notifications
    # asked, tabs from links after the current one's, new tabs at the end,
    # and page colors never.
    prefs = {
        'settings': {'a11y': {'animation_policy': 'none', 'requested_page_colors': 1}},
        'oganesson': {'tabs': {'link_position': 1}},
        'helium': {'browser': {'new_tab_next_to_active': False}},
    }
    hosts = ('example.com',)
    routes = {
        '/test_update.json': (200, {'Content-Type': 'application/json'}, json.dumps({
            'addons': {
                SETTINGS_ID: {
                    'updates': [
                        {
                            'version': '2.0',
                            'update_link':
                                'http://example.com/addons/test_settings_staged_restart_v2.xpi',
                        },
                    ],
                },
            },
        }).encode()),
        '/addons/test_settings_staged_restart_v2.xpi':
            (200, {'Content-Type': 'application/x-xpinstall'}, UPDATE_XPI),
    }

    def preference(self, name):
        """Preferences.get(name), for a pref in FIREFOX_PREFS."""
        return FIREFOX_PREFS[name](self.browser.profile_prefs())

    def test_01_browser_settings(self):
        extension = self.load_extension(
            background=JS('''async function background() {
    let listeners = new Set([]);
    browser.test.onMessage.addListener(async (msg, apiName, value) => {
      let apiObj = browser.browserSettings;
      let apiNameSplit = apiName.split(".");
      for (let apiPart of apiNameSplit) {
        apiObj = apiObj[apiPart];
      }
      if (msg == "get") {
        browser.test.sendMessage("settingData", await apiObj.get({}));
        return;
      }

      // set and setNoOp

      // Don't add more than one listner per apiName.  We leave the
      // listener to ensure we do not get more calls than we expect.
      if (!listeners.has(apiName)) {
        apiObj.onChange.addListener(details => {
          browser.test.sendMessage("onChange", {
            details,
            setting: apiName,
          });
        });
        listeners.add(apiName);
      }
      let result = await apiObj.set({ value });
      if (msg === "set") {
        browser.test.assertTrue(result, "set returns true.");
        browser.test.sendMessage("settingData", await apiObj.get({}));
      } else {
        browser.test.assertFalse(result, "set returns false for a no-op.");
        browser.test.sendMessage("no-op set");
      }
    });
  }'''),
            manifest={
                'permissions': ['browserSettings'],
            })

        extension.startup()

        def test_setting(setting, value, expected, expected_value=None):
            if expected_value is None:
                expected_value = value
            extension.send_message('set', setting, value)
            data = extension.await_message('settingData')
            data_change = extension.await_message('onChange')
            self.is_(setting, data_change['setting'], 'onChange fired')
            self.is_(data['value'], data_change['details']['value'],
                     'onChange fired with correct value')
            self.is_(data['value'], expected_value,
                     f'The {setting} setting has the expected value.')
            self.is_(data['levelOfControl'], 'controlled_by_this_extension',
                     f'The {setting} setting has the expected levelOfControl.')
            for pref in expected:
                if pref in FIREFOX_PREFS:
                    self.is_(self.preference(pref), expected[pref],
                             f'{pref} set correctly for {value}')

        test_setting('cacheEnabled', False, {
            'browser.cache.disk.enable': False,
            'browser.cache.memory.enable': False,
        })
        test_setting('cacheEnabled', True, {
            'browser.cache.disk.enable': True,
            'browser.cache.memory.enable': True,
        })

        test_setting('allowPopupsForUserEvents', False, {
            'dom.popup_allowed_events': '',
        })
        test_setting('allowPopupsForUserEvents', True, {
            'dom.popup_allowed_events': None,
        })

        for value in ['normal', 'none', 'once']:
            test_setting('imageAnimationBehavior', value, {
                'image.animation_mode': value,
            })

        test_setting('webNotificationsDisabled', True, {
            'permissions.default.desktop-notification': PERM_DENY_ACTION,
        })
        test_setting('webNotificationsDisabled', False, {
            'permissions.default.desktop-notification': PERM_UNKNOWN_ACTION,
        })

        # Linux: neither Android nor Windows.
        test_setting('contextMenuShowEvent', 'mouseup', {
            'ui.context_menus.after_mouseup': True,
        })
        test_setting('contextMenuShowEvent', 'mousedown', {
            'ui.context_menus.after_mouseup': False,
        })

        test_setting('closeTabsByDoubleClick', True, {
            'browser.tabs.closeTabByDblclick': True,
        })
        test_setting('closeTabsByDoubleClick', False, {
            'browser.tabs.closeTabByDblclick': False,
        })

        extension.send_message('get', 'ftpProtocolEnabled')
        data = extension.await_message('settingData')
        self.is_(data['value'], False, 'ftpProtocolEnabled is false')
        self.is_(data['levelOfControl'], 'not_controllable',
                 'ftpProtocolEnabled is not controllable.')

        test_setting('newTabPosition', 'afterCurrent', {
            'browser.tabs.insertRelatedAfterCurrent': False,
            'browser.tabs.insertAfterCurrent': True,
        })
        test_setting('newTabPosition', 'atEnd', {
            'browser.tabs.insertRelatedAfterCurrent': False,
            'browser.tabs.insertAfterCurrent': False,
        })
        test_setting('newTabPosition', 'relatedAfterCurrent', {
            'browser.tabs.insertRelatedAfterCurrent': True,
            'browser.tabs.insertAfterCurrent': False,
        })

        test_setting('openBookmarksInNewTabs', True, {
            'browser.tabs.loadUILinkInTab': True,
        })
        test_setting('openBookmarksInNewTabs', False, {
            'browser.tabs.loadUILinkInTab': False,
        })

        test_setting('openSearchResultsInNewTabs', True, {
            'browser.search.openintab': True,
        })
        test_setting('openSearchResultsInNewTabs', False, {
            'browser.search.openintab': False,
        })

        test_setting('openUrlbarResultsInNewTabs', True, {
            'browser.urlbar.openintab': True,
        })
        test_setting('openUrlbarResultsInNewTabs', False, {
            'browser.urlbar.openintab': False,
        })

        test_setting('overrideDocumentColors', 'high-contrast-only', {
            'browser.display.document_color_use': 0,
        })
        test_setting('overrideDocumentColors', 'never', {
            'browser.display.document_color_use': 1,
        })
        test_setting('overrideDocumentColors', 'always', {
            'browser.display.document_color_use': 2,
        })

        test_setting('overrideContentColorScheme', 'dark', {
            'layout.css.prefers-color-scheme.content-override': 0,
        })
        test_setting('overrideContentColorScheme', 'light', {
            'layout.css.prefers-color-scheme.content-override': 1,
        })
        test_setting('overrideContentColorScheme', 'auto', {
            'layout.css.prefers-color-scheme.content-override': 2,
        })

        test_setting('useDocumentFonts', False, {
            'browser.display.use_document_fonts': 0,
        })
        test_setting('useDocumentFonts', True, {
            'browser.display.use_document_fonts': 1,
        })

        test_setting('zoomFullPage', True, {
            'browser.zoom.full': True,
        })
        test_setting('zoomFullPage', False, {
            'browser.zoom.full': False,
        })

        test_setting('zoomSiteSpecific', True, {
            'browser.zoom.siteSpecific': True,
        })
        test_setting('zoomSiteSpecific', False, {
            'browser.zoom.siteSpecific': False,
        })

        test_setting('colorManagement.mode', 'off', {
            'gfx.color_management.mode': 0,
        })
        test_setting('colorManagement.mode', 'full', {
            'gfx.color_management.mode': 1,
        })
        test_setting('colorManagement.mode', 'tagged_only', {
            'gfx.color_management.mode': 2,
        })

        test_setting('colorManagement.useNativeSRGB', False, {
            'gfx.color_management.native_srgb': False,
        })
        test_setting('colorManagement.useNativeSRGB', True, {
            'gfx.color_management.native_srgb': True,
        })

        test_setting('colorManagement.useWebRenderCompositor', False, {
            'gfx.webrender.compositor': False,
        })
        test_setting('colorManagement.useWebRenderCompositor', True, {
            'gfx.webrender.compositor': True,
        })

        test_setting('verticalTabs', False, {
            'sidebar.verticalTabs': False,
        })
        test_setting('verticalTabs', True, {
            'sidebar.verticalTabs': True,
        })

        extension.unload()

    def test_02_bad_value(self):
        extension = self.load_extension(
            background=JS('''async function background() {
    await browser.test.assertRejects(
      browser.browserSettings.contextMenuShowEvent.set({ value: "bad" }),
      /bad is not a valid value for contextMenuShowEvent/,
      "contextMenuShowEvent.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.overrideDocumentColors.set({ value: 2 }),
      /2 is not a valid value for overrideDocumentColors/,
      "overrideDocumentColors.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.overrideDocumentColors.set({ value: "bad" }),
      /bad is not a valid value for overrideDocumentColors/,
      "overrideDocumentColors.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.overrideContentColorScheme.set({ value: 0 }),
      /0 is not a valid value for overrideContentColorScheme/,
      "overrideContentColorScheme.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.overrideContentColorScheme.set({ value: "bad" }),
      /bad is not a valid value for overrideContentColorScheme/,
      "overrideContentColorScheme.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.zoomFullPage.set({ value: 0 }),
      /0 is not a valid value for zoomFullPage/,
      "zoomFullPage.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.zoomFullPage.set({ value: "bad" }),
      /bad is not a valid value for zoomFullPage/,
      "zoomFullPage.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.zoomSiteSpecific.set({ value: 0 }),
      /0 is not a valid value for zoomSiteSpecific/,
      "zoomSiteSpecific.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.zoomSiteSpecific.set({ value: "bad" }),
      /bad is not a valid value for zoomSiteSpecific/,
      "zoomSiteSpecific.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.verticalTabs.set({ value: 0 }),
      /0 is not a valid value for verticalTabs/,
      "verticalTabs.set rejects with an invalid value."
    );

    await browser.test.assertRejects(
      browser.browserSettings.verticalTabs.set({ value: "bad" }),
      /bad is not a valid value for verticalTabs/,
      "verticalTabs.set rejects with an invalid value."
    );

    browser.test.sendMessage("done");
  }'''),
            manifest={
                'permissions': ['browserSettings'],
            })

        extension.startup()
        extension.await_message('done')
        extension.unload()

    def test_03_bad_value_android(self):
        # Firefox's task runs only on Android.
        pass

    def test_04_delay_updates_settings_after_restart(self):
        # Verifies settings remain after a staged update on restart.
        extension = self.load_extension(
            use_addon_manager='permanent',
            manifest={
                'version': '1.0',
                'browser_specific_settings': {
                    'gecko': {
                        'id': SETTINGS_ID,
                        'update_url': 'http://example.com/test_update.json',
                    },
                },
                'permissions': ['browserSettings'],
            },
            background=JS('''function() {
      browser.runtime.onUpdateAvailable.addListener(async details => {
        if (details) {
          await browser.browserSettings.webNotificationsDisabled.set({
            value: true,
          });
          if (details.version) {
            // This should be the version of the pending update.
            browser.test.assertEq("2.0", details.version, "correct version");
            browser.test.notifyPass("delay");
          }
        } else {
          browser.test.fail("no details object passed");
        }
      });
      browser.test.sendMessage("ready");
    }'''))

        extension.startup()
        extension.await_message('ready')

        prefname = 'permissions.default.desktop-notification'
        val = self.preference(prefname)
        self.assertNotEqual(val, PERM_DENY_ACTION, 'webNotificationsDisabled pref not set')

        # The user checks for updates.
        page = self.open_tab('chrome://extensions')
        try:
            wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
            page.eval('chrome.developerPrivate.autoUpdate()')
        finally:
            self.browser.close_target(page)

        extension.await_finish('delay')

        # restarting allows upgrade to proceed
        self.restart_browser()

        # extension.awaitStartup(): the update, which has no background.
        page = self.open_tab('chrome://extensions')
        try:
            wait_for(lambda: page.eval(f'chrome.management.get({json.dumps(extension.id)})'
                                       '.then(e => e.version)') == '2.0',
                     what='the update to start')
        finally:
            self.browser.close_target(page)

        # If an update is not handled correctly we would fail here.  Bug 1639705.
        val = self.preference(prefname)
        self.assertEqual(val, PERM_DENY_ACTION, 'webNotificationsDisabled pref set')

        extension.unload()

        val = self.preference(prefname)
        self.assertNotEqual(val, PERM_DENY_ACTION, 'webNotificationsDisabled pref not set')
