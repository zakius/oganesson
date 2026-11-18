"""Port of Firefox's
browser/components/extensions/test/xpcshell/test_ext_manifest.js
(test_ext_manifest_browser.py, since toolkit's test_ext_manifest.js is
test_ext_manifest.py).

Firefox's `ExtensionTestUtils.normalizeManifest()` is loading the add-on
(normalize_manifest()): a manifest error is the browser's refusal to load it,
with the refusal's text, and the manifest's warnings (`normalized.errors`) are
the add-on's install warnings, which chrome://extensions shows.

Left out, as a Gecko internal: ExtensionTestUtils.failOnSchemaWarnings(),
which keeps Firefox's test harness from failing on a manifest warning.
"""

import json
import re

from extension_test_utils import FirefoxTest

ALL_ACTIONS = [
    'action',
    'browser_action',
    'page_action',
    'sidebar_action',
]


class ManifestBrowserTest(FirefoxTest):

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

    def test_01_manifest(self):
        badpaths = ['', ' ', '\t', 'http://foo.com/icon.png']
        for path in badpaths:
            for action in ALL_ACTIONS:
                manifest_version = 3 if action == 'action' else 2
                manifest = {'manifest_version': manifest_version}
                manifest[action] = {'default_icon': path}
                error = f'Error processing {action}.default_icon'
                self.check_manifest(manifest, error)

                manifest[action] = {'default_icon': {'16': path}}
                self.check_manifest(manifest, error)

        paths = [
            'icon.png',
            '/icon.png',
            './icon.png',
            'path to an icon.png',
            ' icon.png',
        ]
        for path in paths:
            for action in ALL_ACTIONS:
                manifest_version = 3 if action == 'action' else 2
                manifest = {'manifest_version': manifest_version}
                manifest[action] = {'default_icon': path}
                if action == 'sidebar_action':
                    # Sidebar requires panel.
                    manifest[action]['default_panel'] = 'foo.html'
                self.check_manifest(manifest)

                manifest[action] = {'default_icon': {'16': path}}
                if action == 'sidebar_action':
                    manifest[action]['default_panel'] = 'foo.html'
                self.check_manifest(manifest)

    def test_02_action_version(self):
        warnings = self.check_manifest({
            'manifest_version': 3,
            'browser_action': {
                'default_panel': 'foo.html',
            },
        })
        self.is_(warnings, ['Property "browser_action" is unsupported in Manifest Version 3'],
                 'Manifest v3 with "browser_action" key logs an error.')

        warnings = self.check_manifest({
            'manifest_version': 2,
            'action': {
                'default_icon': '',
                'default_panel': 'foo.html',
            },
        })
        self.is_(warnings, ['Property "action" is unsupported in Manifest Version 2'],
                 'Manifest v2 with "action" key first warning is clear.')

    # Verify that extended F13-F19 keys are invalid when specified in the
    # extensions manifest.
    #
    # Other related tests:
    # - browser_manage_shortcuts.js include a test that makes sure the F13-F19
    #   keys are valid when assigned by a user through about:addons "Manage
    #   Shortcuts".
    # - browser_ext_commands_update.js include a test that makes sure the
    #   F13-F19 keys are valid when dynamically assigned by the extension
    #   through browser.commands.update API calls.
    def test_03_invalid_extended_function_keys(self):
        # Verify F13-19 are invalid when assigned from the extension manifest
        normalized = self.normalize_manifest({
            'commands': {
                'invalidFnKeyCommand': {
                    'suggested_key': {
                        'default': 'Alt+F13',
                    },
                },
            },
        })
        expected_error = ('Value ".*" must not include extended F13-F19 keys. '
                          'F13-F19 keys can only be used for user-defined keyboard shortcuts')
        self.check(normalized['error'] and re.search(expected_error, normalized['error']),
                   'Should have reported F13 as an invalid key manifest error, got: '
                   f"{normalized['error']}")
