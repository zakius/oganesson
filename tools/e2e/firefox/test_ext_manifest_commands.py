"""Port of Firefox's
browser/components/extensions/test/xpcshell/test_ext_manifest_commands.js.

Firefox's `ExtensionTestUtils.normalizeManifest()` is loading the add-on: a
manifest error is the browser's refusal to load it, with the error's text.
"""

from extension_test_utils import FirefoxTest


class ManifestCommandsTest(FirefoxTest):

    def validate_shortcut(self, shortcut, is_valid):
        extension = self.load_extension(manifest={
            'commands': {
                'toggle-feature': {
                    'suggested_key': {'default': shortcut},
                    'description': "Send a 'toggle-feature' event to the extension",
                },
            },
        })
        try:
            extension.startup()
            error = None
        except RuntimeError as refused:
            error = str(refused)
        if is_valid:
            self.check(not error, f'{shortcut}: There should be no manifest errors. - Actual: {error}')
        else:
            expected_error = (
                'Error processing commands.toggle-feature.suggested_key.default: Error: '
                f'Value "{shortcut}" must consist of '
                'either a combination of one or two modifiers, including '
                "a mandatory primary modifier and a key, separated by '+', "
                'or a media key. For details see: '
                'https://developer.mozilla.org/en-US/Add-ons/WebExtensions/manifest.json/commands#Key_combinations')
            self.check(error and expected_error in error,
                       f'The manifest error {error!r} must contain {expected_error!r}')
        if not error:
            extension.unload()

    def test_01_manifest_commands(self):
        valid_shortcuts = [
            'Ctrl+Y',
            'MacCtrl+Y',
            'Command+Y',
            'Alt+Shift+Y',
            'Ctrl+Alt+Y',
            'F1',
            'MediaNextTrack',
        ]
        invalid_shortcuts = ['Shift+Y', 'Y', 'Ctrl+Ctrl+Y', 'Ctrl+Command+Y']

        for shortcut in valid_shortcuts:
            self.validate_shortcut(shortcut, True)
        for shortcut in invalid_shortcuts:
            self.validate_shortcut(shortcut, False)
