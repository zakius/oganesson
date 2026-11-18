"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_browserAction_simple.js.

clickBrowserAction() is a real click on the add-on's toolbar button, pinned,
and closeBrowserAction() closes the popup. Firefox reads the button's icon
URL; the button has no URL, so the port gives icon.png a colour of its own
and reads it on the button (head.action_button_state()), before each click:
while its popup is open, the button shows it pressed. Firefox's console
warning for the manifest's unknown property is one of the add-on's install
warnings here, as chrome://extensions shows them. Left out:
ExtensionTestUtils.failOnSchemaWarnings() and the widget's `webExtension`
property, Gecko internals. The add-on's code is Firefox's, as it is.
"""

from firefox import head
from extension_test_utils import JS, FirefoxTest
from test_importer import png

ICON = (255, 0, 0)


class BrowserActionSimpleTest(FirefoxTest):

    def run_action(self, manifest_version):
        """testAction()."""
        action = 'browser_action' if manifest_version < 3 else 'action'
        extension = self.load_extension(
            manifest={
                'manifest_version': manifest_version,
                action: {
                    'default_popup': 'popup.html',
                    'default_area': 'navbar',
                    'unrecognized_property': 'with-a-random-value',
                },
                'icons': {'32': 'icon.png'},
            },
            files={
                'popup.html': '''
      <!DOCTYPE html>
      <html><body>
      <script src="popup.js"></script>
      </body></html>
      ''',
                'popup.js': JS('''function () {
        window.onload = () => {
          browser.runtime.sendMessage("from-popup");
        };
      }'''),
                'icon.png': png(ICON),
            },
            background=JS('''function () {
      browser.runtime.onMessage.addListener(msg => {
        browser.test.assertEq(msg, "from-popup", "correct message received");
        browser.test.sendMessage("popup");
      });

      // Test what api namespace is valid, make sure both are not.
      let manifest = browser.runtime.getManifest();
      let { manifest_version } = manifest;
      browser.test.assertEq(
        manifest_version == 2,
        "browserAction" in browser,
        "browserAction is available"
      );
      browser.test.assertEq(
        manifest_version !== 2,
        "action" in browser,
        "action is available"
      );
    }'''))
        extension.startup()

        # Do this a few times to make sure the pop-up is reloaded each time.
        for _ in range(3):
            state = head.action_button_state(self, {'icon.png': ICON})
            self.is_(state['icon'], 'icon.png', "The extension's icon is used")
            popup = self.browser.open_popup(extension.id)
            extension.await_message('popup')
            self.browser.close_target(popup)

        warnings = self.browser.extension_info(extension.id)['installWarnings']
        expected = (f'Reading manifest: Warning processing {action}.unrecognized_property: '
                    'An unexpected property was found')
        self.check(any(expected in warning for warning in warnings),
                   f'{expected} - Expected: the warning, Actual: {warnings}')
        extension.unload()

    def test_01_browser_action(self):
        self.run_action(2)

    def test_02_action(self):
        self.run_action(3)
