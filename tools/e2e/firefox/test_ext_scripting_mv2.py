"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_scripting_mv2.js."""

from extension_test_utils import JS, FirefoxTest


class ScriptingMv2Test(FirefoxTest):

    def test_01_scripting_enabled_in_mv2(self):
        extension = self.load_extension(
            manifest={
                'manifest_version': 2,
                'permissions': ['scripting'],
            },
            background=JS('''function() {
              browser.test.assertEq(
                "object",
                typeof browser.scripting,
                "expected scripting namespace to be defined"
              );

              browser.test.sendMessage("background-done");
            }'''))
        extension.startup()
        extension.await_message('background-done')
        extension.unload()
