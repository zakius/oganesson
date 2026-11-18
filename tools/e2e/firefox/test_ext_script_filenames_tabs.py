"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_script_filenames.html.

The add-on's code is Firefox's, as it is. mochi.test's page comes from a
local server, and AppTestDelegate's new foreground tab is a tab here."""

from extension_test_utils import JS, FirefoxTest

HTML = {'Content-Type': 'text/html'}


class ScriptFilenamesTabsTest(FirefoxTest):
    hosts = ('mochi.test',)
    routes = {'/': (200, HTML, b'<!DOCTYPE html><title>mochi.test</title>')}

    def test_01_tabs_executeScript(self):
        valid_file_name = 'script.js'
        invalid_file_name = 'script.xyz'

        background = JS('''async function background() {
    await browser.tabs.executeScript({ file: "script.js" });

    await browser.test.assertRejects(
      browser.tabs.executeScript({ file: "script.xyz" }),
      Error,
      "invalid filename does not execute"
    );
    browser.test.notifyPass("execute-script");
  }''')

        extension = self.load_extension(
            manifest={
                'permissions': ['<all_urls>'],
            },
            background=background,
            files={
                valid_file_name: JS('''function contentScript1() {
        browser.test.sendMessage("content-script-loaded");
      }'''),
                invalid_file_name: JS('''function contentScript2() {
        browser.test.fail("this script should not be loaded");
      }'''),
            })

        tab = self.open_tab('http://mochi.test:8888/')
        extension.startup()

        extension.await_message('content-script-loaded')
        extension.await_finish('execute-script')

        extension.unload()
        self.browser.close_target(tab)
