"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_manifest.js.

Firefox's `ExtensionTestUtils.normalizeManifest()` is loading the add-on
(normalize_manifest()): a manifest error is the browser's refusal to load it,
with the refusal's text, and the manifest's warnings (`normalized.errors`,
`extension.extension.warnings`) are the add-on's install warnings, which
chrome://extensions shows. The add-on's name and update URL are what
chrome://extensions shows too. AddonManager.getAddonByID() is the add-on that
chrome.management lists, and the add-on that Firefox finds by its Gecko ID is
the one whose ID this browser takes from that Gecko ID. The theme's
`extension.state`, "Startup: Complete", is that chrome.management lists it
enabled. Firefox's app version, 42 in the test, is this browser's version,
which `runtime.getBrowserInfo()` gives as Firefox's: each version range that
test_bss_gecko_android gives is below either. This is the desktop browser
(AppConstants.platform isn't "android"), so the port expects Firefox's errors
off Android, and skips the cases that Firefox skips there. Firefox's test
fetches the theme's bg.png from its own scope; here a tab at the file's URL
fetches it.

Left out, as Gecko internals: ExtensionTestUtils.failOnSchemaWarnings(),
which keeps Firefox's test harness from failing on a manifest warning, and
the AddonTestUtils app info and add-on manager start-up (add_setup()).
test_bss_gecko_android_only isn't ported: Firefox runs it only on Android.
"""

import json
import re

from extension_test_utils import FirefoxTest
from harness import extension_id, wait_for


class ManifestTest(FirefoxTest):

    def check_manifest(self, manifest, expected_error=None):
        """Firefox's testManifest()."""
        normalized = self.normalize_manifest(manifest)
        if expected_error:
            self.check(normalized['error'] and re.search(expected_error, normalized['error']),
                       f"Should have an error for {json.dumps(manifest)}, got {normalized['error']}")
        else:
            self.check(not normalized['error'],
                       f"Should not have an error {json.dumps(manifest)}, {normalized['error']}")
        return normalized['errors']

    def check_icon_paths(self, icon, manifest, expected_error=None):
        """Firefox's testIconPaths()."""
        normalized = self.normalize_manifest(manifest)
        if expected_error:
            self.check(normalized['error'] and re.search(expected_error, normalized['error']),
                       f"Should have an error for {json.dumps(icon)} - Actual: {normalized['error']}")
        else:
            self.check(not normalized['error'],
                       f"Should not have an error {json.dumps(icon)} - Actual: {normalized['error']}")

    def get_addon_by_id(self, addon_id):
        """AddonManager.getAddonByID(): the add-on's chrome.management
        ExtensionInfo, which has themes too, or None."""
        page = self.browser.new_tab('chrome://extensions')
        try:
            wait_for(lambda: page.eval('!!chrome.management'), what='chrome://extensions')
            return page.eval('chrome.management.getAll()'
                             f'.then(all => all.find(e => e.id == {json.dumps(addon_id)}) ?? null)')
        finally:
            self.browser.close_target(page)

    def test_01_manifest(self):
        badpaths = ['', ' ', '\t', 'http://foo.com/icon.png']
        for path in badpaths:
            self.check_icon_paths(path, {'icons': path}, 'Error processing icons')
            self.check_icon_paths(path, {'icons': {'16': path}}, 'Error processing icons')

        paths = [
            'icon.png',
            '/icon.png',
            './icon.png',
            'path to an icon.png',
            ' icon.png',
        ]
        for path in paths:
            # manifest.icons is an object
            self.check_icon_paths(path, {'icons': path}, 'Error processing icons')
            self.check_icon_paths(path, {'icons': {'16': path}})

    def test_02_manifest_warnings_on_unexpected_props(self):
        extension = self.load_extension(
            manifest={
                'background': {
                    'scripts': ['bg.js'],
                    'wrong_prop': True,
                },
            },
            files={'bg.js': ''})
        extension.startup()

        # The warnings that chrome://extensions shows.
        warnings = self.browser.extension_info(extension.id)['installWarnings']
        self.is_(len(warnings), 1, 'Got the expected number of manifest warnings')

        expected_message = 'Reading manifest: Warning processing background.wrong_prop'
        self.check(len(warnings) > 0 and warnings[0].startswith(expected_message),
                   f'Got the expected warning message format - Actual: {warnings}')

        extension.unload()

    def test_03_mv2_scripting_permission_always_enabled(self):
        warnings = self.check_manifest({
            'manifest_version': 2,
            'permissions': ['scripting'],
        })
        self.is_(warnings, [], 'Got no warnings')

    def test_04_mv3_scripting_permission_always_enabled(self):
        warnings = self.check_manifest({
            'manifest_version': 3,
            'permissions': ['scripting'],
        })
        self.is_(warnings, [], 'Got no warnings')

    def test_05_name_too_long(self):
        extension = self.load_extension(manifest={
            # This length is 80, which exceeds ExtensionData.EXT_NAME_MAX_LEN:
            'name': '123456789_' * 8,
        })
        extension.startup()
        info = self.browser.extension_info(extension.id)
        self.is_(info['name'],
                 '123456789_123456789_123456789_123456789_123456789_123456789_123456789_12345',
                 'Name should be truncated')
        self.is_(info['installWarnings'],
                 ['Reading manifest: Warning processing "name": must be shorter than 75'],
                 'Expected error message when the name is too long')
        extension.unload()

    def test_06_simpler_version_format(self):
        test_cases = [
            # Valid cases
            ('0', False),
            ('0.0', False),
            ('0.0.0', False),
            ('0.0.0.0', False),
            ('0.0.0.1', False),
            ('0.0.0.999999999', False),
            ('0.0.1.0', False),
            ('0.0.999999999', False),
            ('0.1.0.0', False),
            ('0.999999999', False),
            ('1', False),
            ('1.0', False),
            ('1.0.0', False),
            ('1.0.0.0', False),
            ('1.2.3.4', False),
            ('999999999', False),
            ('999999999.999999999.999999999.999999999', False),
            # Invalid cases
            ('.', True),
            ('.999999999', True),
            ('0.0.0.0.0', True),
            ('0.0.0.00001', True),
            ('0.0.0.0010', True),
            ('0.0.00001', True),
            ('0.0.001', True),
            ('0.0.01.0', True),
            ('0.01.0', True),
            ('00001', True),
            ('0001', True),
            ('001', True),
            ('01', True),
            ('01.0', True),
            ('099999', True),
            ('0999999999', True),
            ('1.00000', True),
            ('1.1.-1', True),
            ('1.1000000000', True),
            ('1.1pre1aa', True),
            ('1.2.1000000000', True),
            ('1.2.3.4-a', True),
            ('1.2.3.4.5', True),
            ('1000000000', True),
            ('1000000000.0.0.0', True),
            ('999999999.', True),
        ]

        for version, expect_warning in test_cases:
            normalized = self.normalize_manifest({'version': version})

            if expect_warning:
                self.is_(normalized['errors'],
                         ['Warning processing version: version must be a version string '
                          'consisting of at most 4 integers of at most 9 digits without '
                          'leading zeros, and separated with dots'],
                         f'expected warning for version: {version}')
            else:
                self.is_(normalized['errors'], [], f'expected no warning for version: {version}')

    def test_07_applications(self):
        addon_id = 'some@id'
        update_url = 'https://example.com/updates/'

        extension = self.load_extension(
            manifest={
                'manifest_version': 2,
                'applications': {
                    'gecko': {'id': addon_id, 'update_url': update_url},
                },
            },
            use_addon_manager='temporary')
        extension.startup()

        info = self.browser.extension_info(extension.id)
        self.is_(info['installWarnings'], [], 'expected no warnings')

        # The ID that the browser takes from the Gecko ID: the manifest has no
        # other.
        self.is_(extension.id, extension_id(extension.folder), 'got expected ID')
        self.is_(info['updateUrl'], update_url, 'got expected update URL')

        extension.unload()

    def test_08_applications_key_mv3(self):
        warnings = self.check_manifest({
            'manifest_version': 3,
            'applications': {},
        })
        self.is_(warnings, ['Property "applications" is unsupported in Manifest Version 3'],
                 'Manifest v3 with "applications" key logs an error.')

    def test_09_bss_gecko_android(self):
        addon_id = 'some@id'

        test_cases = [
            {
                'title': 'gecko_android overrides gecko',
                'browser_specific_settings': {
                    'gecko': {
                        'id': addon_id,
                        'strict_min_version': '2',
                        'strict_max_version': '2',
                    },
                    'gecko_android': {
                        'strict_min_version': '1',
                        'strict_max_version': '1',
                    },
                },
                'expected_error': f'Add-on {addon_id} is not compatible with application version. '
                                  'add-on minVersion: 2. add-on maxVersion: 2.',
            },
            {
                'title': 'strict_min_version in gecko_android overrides gecko.strict_min_version',
                'browser_specific_settings': {
                    'gecko': {
                        'id': addon_id,
                        'strict_min_version': '2',
                        'strict_max_version': '3',
                    },
                    'gecko_android': {
                        'strict_min_version': '3',
                    },
                },
                'expected_error': f'Add-on {addon_id} is not compatible with application version. '
                                  'add-on minVersion: 2. add-on maxVersion: 3.',
            },
            {
                'title': 'strict_max_version in gecko_android overrides gecko.strict_max_version',
                'browser_specific_settings': {
                    'gecko': {
                        'id': addon_id,
                        'strict_min_version': '2',
                        'strict_max_version': '2',
                    },
                    'gecko_android': {
                        'strict_max_version': '3',
                    },
                },
                'expected_error': f'Add-on {addon_id} is not compatible with application version. '
                                  'add-on minVersion: 2. add-on maxVersion: 2.',
            },
            {
                'title': 'no gecko_android',
                'browser_specific_settings': {
                    'gecko': {
                        'id': addon_id,
                        'strict_min_version': '2',
                        'strict_max_version': '2',
                    },
                },
                'expected_error': f'Add-on {addon_id} is not compatible with application version. '
                                  'add-on minVersion: 2. add-on maxVersion: 2.',
            },
            {
                'title': 'empty gecko_android',
                'browser_specific_settings': {
                    'gecko': {
                        'id': addon_id,
                        'strict_min_version': '2',
                        'strict_max_version': '2',
                    },
                    'gecko_android': {},
                },
                'expected_error': f'Add-on {addon_id} is not compatible with application version. '
                                  'add-on minVersion: 2. add-on maxVersion: 2.',
            },
            {
                'title': 'empty strict min/max versions in gecko_android',
                'browser_specific_settings': {
                    'gecko': {
                        'id': addon_id,
                        'strict_min_version': '2',
                        'strict_max_version': '2',
                    },
                    'gecko_android': {
                        'strict_min_version': '',
                        'strict_max_version': '',
                    },
                },
                'expected_error': f'Add-on {addon_id} is not compatible with application version. '
                                  'add-on minVersion: 2. add-on maxVersion: 2.',
            },
            {
                'title': 'only strict min/max version in gecko_android',
                'browser_specific_settings': {
                    'gecko': {
                        'id': addon_id,
                    },
                    'gecko_android': {
                        'strict_min_version': '3',
                        'strict_max_version': '4',
                    },
                },
                'expected_error': None,
            },
            {
                'title': 'only strict_min_version in gecko_android',
                'browser_specific_settings': {
                    'gecko': {
                        'id': addon_id,
                    },
                    'gecko_android': {
                        # The app version is set to `42` at the top of the file.
                        'strict_min_version': '100',
                    },
                },
                'expected_error': None,
            },
        ]

        for case in test_cases:
            title = case['title']
            expected_error = case['expected_error']

            # This task is mainly about verifying `bss.gecko_android` and some
            # test cases require a "valid" compatibility range by default,
            # which would break the assumption below (that the install is
            # going to fail). This is why we skip null errors, but only on
            # non-Android builds.
            if expected_error is None:
                continue

            manifest = {
                'manifest_version': 2,
                'version': '1.0',
                'browser_specific_settings': case['browser_specific_settings'],
            }

            extension = self.load_extension(manifest=manifest, use_addon_manager='temporary')

            try:
                extension.startup()
                error = None
            except RuntimeError as refused:
                error = str(refused)
            self.check(error and re.search(expected_error, error),
                       f'{title} - expected error: {expected_error} - Actual: {error}')

            self.check(self.get_addon_by_id(extension_id(extension.folder)) is None,
                       f'{title} - add-on is not installed')
            # The next case's add-on has the same ID.
            if not error:
                extension.unload()

    # Regression test for https://bugzilla.mozilla.org/show_bug.cgi?id=1542351
    # Test that presence of 'edge' property in 'browser_specific_settings'
    # doesn't prevent installation from completing successfully.
    def test_10_non_gecko_bss_install(self):
        addon_id = 'ms_edge@tests.mozilla.org'

        manifest = {
            'name': 'MS Edge and unknown browser test',
            'description': "extension with bss properties for 'edge', and 'unknown_browser'",
            'manifest_version': 2,
            'version': '1.0',
            'applications': {'gecko': {'id': addon_id}},
            'browser_specific_settings': {
                'edge': {
                    'browser_action_next_to_addressbar': True,
                },
                'unknown_browser': {
                    'unknown_setting': True,
                },
            },
        }

        extension = self.load_extension(manifest=manifest, use_addon_manager='temporary')
        extension.startup()

        self.check(self.get_addon_by_id(extension.id), 'Add-on is installed')
        self.is_(self.browser.extension_info(extension.id)['installWarnings'], [],
                 'expected no warnings')

        extension.unload()

    # Tests that the presence of an unrecognized property in the gecko and
    # gecko_android objects does not prevent successful installation.
    def test_11_gecko_bss_unrecognized_property(self):
        addon_id = 'with-unknown-gecko-prop@tests.mozilla.org'

        manifest = {
            'browser_specific_settings': {
                'gecko': {
                    'id': addon_id,
                    'aPropThatIsNotSupported': 'value does not matter',
                },
                'gecko_android': {
                    'aPropThatIsNotSupported': 'aPropThatIsNotSupported',
                },
            },
        }

        extension = self.load_extension(manifest=manifest, use_addon_manager='temporary')
        extension.startup()

        self.is_(self.browser.extension_info(extension.id)['installWarnings'],
                 [
                     'Reading manifest: Warning processing browser_specific_settings.gecko.'
                     'aPropThatIsNotSupported: An unexpected property was found in the '
                     'WebExtension manifest.',
                     'Reading manifest: Warning processing browser_specific_settings.gecko_android.'
                     'aPropThatIsNotSupported: An unexpected property was found in the '
                     'WebExtension manifest.',
                 ],
                 'Expected warnings about unrecognized properties')

        self.check(self.get_addon_by_id(extension.id), 'Add-on is installed')

        extension.unload()

    def test_12_load_mv3_theme(self):
        background = (
            'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0'
            'DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg==')
        theme = self.load_extension(
            manifest={
                'manifest_version': 3,
                'theme': {},
            },
            use_addon_manager='temporary',
            files={'bg.png': background})
        # This test would hang if there were errors during install.
        theme.startup()
        addon = self.get_addon_by_id(theme.id)
        self.check(addon and addon['enabled'],
                   'Expect theme to have reached the startup completed state')
        # Verify image assets packaged in the theme can be fetched
        url = f'chrome-extension://{theme.id}/bg.png'
        page = self.open_tab(url)
        try:
            fetched = page.eval(f'fetch({json.dumps(url)}).then(r => r.ok, () => false)')
        finally:
            self.browser.close_target(page)
        self.check(fetched, f'{url} can be fetched')
        theme.unload()
