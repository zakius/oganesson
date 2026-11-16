"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_contentscript_dynamic_registration.js.

Firefox's test sends the add-on's registration to the content processes
itself (an override of Extension.broadcast()), and opens the second page
while it does, so that the page's new process starts during the
registration. Left out: that override and its checks of the message it
sends and of the new process's ID, Gecko internals. Here the second page
opens in a new tab once register() has resolved, and the test checks, as
Firefox's does, that the script runs in it and in the first page. The
add-ons' code is Firefox's, as it is."""

from extension_test_utils import JS, FirefoxTest

HTML = {'Content-Type': 'text/html'}
FILE_SAMPLE = b"""<!DOCTYPE HTML>

<html>
<head>
<meta charset="utf-8">
</head>
<body>

<div id="test">Sample text</div>

</body>
</html>
"""
DUMMY_PAGE = b"""<!DOCTYPE html>

<html>
<body>
<p>Page</p>
</body>
</html>
"""


class ContentScriptDynamicRegistrationTest(FirefoxTest):
    routes = {
        '/data/file_sample.html': (200, HTML, FILE_SAMPLE),
        '/data/dummy_page.html': (200, HTML, DUMMY_PAGE),
    }

    def setUp(self):
        super().setUp()
        self.base_url = self.server.url('/data', host='localhost')

    def make_extension(self, background, manifest):
        return self.load_extension(
            manifest={
                **manifest,
                'permissions':
                    ['scripting'] if manifest['manifest_version'] == 3 else ['http://*/*/*.html'],
            },
            background=background,
            files={
                'script.js': JS('''() => {
        browser.test.sendMessage(
          `script-ran: ${location.pathname.split("/").pop()}`
        );
      }'''),
                'inject_browser.js': JS('''() => {
        browser.userScripts.onBeforeScript.addListener(script => {
          // Inject `browser.test.sendMessage()` so that it can be used in the
          // `script.js` defined above when using "user scripts".
          script.defineGlobals({
            browser: {
              test: {
                sendMessage(msg) {
                  browser.test.sendMessage(msg);
                },
              },
            },
          });
        });
      }'''),
            })

    def verify_registration_with_new_process(self, extension):
        extension.startup()
        extension.await_message('background-done')

        second_content_page = self.open_tab(f'{self.base_url}/dummy_page.html')
        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.await_message('script-ran: file_sample.html')
        extension.await_message('script-ran: dummy_page.html')

        # Unload extension first to avoid an issue on Windows platforms.
        extension.unload()
        self.browser.close_target(content_page)
        self.browser.close_target(second_content_page)

    def test_01_scripting_registerContentScripts(self):
        extension = self.make_extension(
            manifest={
                'manifest_version': 3,
                'host_permissions': ['<all_urls>'],
                'granted_host_permissions': True,
            },
            background=JS('''async function background() {
      const script = {
        id: "a-script",
        js: ["script.js"],
        matches: ["http://*/*/*.html"],
        persistAcrossSessions: false,
      };

      await browser.scripting.registerContentScripts([script]);

      browser.test.sendMessage("background-done");
    }'''))

        self.verify_registration_with_new_process(extension)

    def test_02_contentScripts_register(self):
        extension = self.make_extension(
            manifest={
                'manifest_version': 2,
            },
            background=JS('''async function background() {
        await browser.contentScripts.register({
          js: [{ file: "script.js" }],
          matches: ["http://*/*/*.html"],
        });

        browser.test.sendMessage("background-done");
      }'''))

        self.verify_registration_with_new_process(extension)

    def test_03_userScripts_register(self):
        extension = self.make_extension(
            manifest={
                'manifest_version': 2,
                'user_scripts': {
                    'api_script': 'inject_browser.js',
                },
            },
            background=JS('''async function background() {
        await browser.userScripts.register({
          js: [{ file: "script.js" }],
          matches: ["http://*/*/*.html"],
        });

        browser.test.sendMessage("background-done");
      }'''))

        self.verify_registration_with_new_process(extension)
