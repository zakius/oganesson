"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_runtime_getBrowserInfo.js.

Firefox's test first mocks the app's info (name "XPCShell", vendor "Mozilla",
version "48", build ID "20160315") with ExtensionTestUtils.mockAppInfo(). This
browser's info can't be mocked, so the add-on is told the browser's own, as
`--version` gives it: the product's name as name and vendor, and Chromium's
version as version and build ID (dubna's firefox_runtime_api.cc)."""

import json
import subprocess

from extension_test_utils import JS, FirefoxTest


class GetBrowserInfoTest(FirefoxTest):

    def test_01_getBrowserInfo(self):
        out = subprocess.run([str(self.browser.binary), '--version'], capture_output=True,
                             text=True, check=True).stdout.split()
        name, version = out[0], out[1]
        background = JS('''async function background(name, version) {
            let info = await browser.runtime.getBrowserInfo();

            browser.test.assertEq(info.name, name, "name is valid");
            browser.test.assertEq(info.vendor, name, "vendor is the browser's");
            browser.test.assertEq(info.version, version, "version is correct");
            browser.test.assertEq(info.buildID, version, "buildID is correct");

            browser.test.notifyPass("runtime.getBrowserInfo");
          }''', json.dumps(name), json.dumps(version))
        extension = self.load_extension(background=background)
        extension.startup()
        extension.await_finish('runtime.getBrowserInfo')
        extension.unload()
