"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_script_filenames.js.

The add-ons' code is Firefox's, as it is. Firefox's content page
(ExtensionTestUtils.loadContentPage()) is a tab here. Left out:
PromiseTestUtils.allowMatchingRejectionsGlobally(), which lets Gecko's
rejection for a script that fails to load pass in Firefox's test harness; it
checks nothing."""

import base64
import hashlib

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

# This function represents a dummy content or background script that the test
# cases below should attempt to load but it shouldn't be loaded because we
# check the extensions of JavaScript files in `nsJARChannel`.
SCRIPT_THAT_SHOULD_NOT_BE_LOADED = JS('''function scriptThatShouldNotBeLoaded() {
  browser.test.fail("this should not be executed");
}''')

SCRIPT_THAT_ALWAYS_RUNS = JS('''function scriptThatAlwaysRuns() {
  browser.test.sendMessage("content-script-loaded");
}''')

# We use these variables in combination with `scriptThatAlwaysRuns()` to send a
# signal to the extension and avoid the page to be closed too soon.
ALWAYS_RUNS_FILE_NAME = 'always_run.js'
ALWAYS_RUNS_CONTENT_SCRIPT = {
    'matches': ['<all_urls>'],
    'js': [ALWAYS_RUNS_FILE_NAME],
    'run_at': 'document_start',
}


def compute_sha256_hash(text):
    """The base64 SHA-256 hash of `text`, as Firefox's computeSHA256Hash()."""
    digest = hashlib.sha256(text.encode('latin-1')).digest()
    return base64.b64encode(digest).decode()


class ScriptFilenamesTest(FirefoxTest):
    routes = {'/data/file_sample.html': (200, HTML, FILE_SAMPLE)}

    def setUp(self):
        super().setUp()
        self.base_url = self.server.url('/data', host='localhost')

    def test_01_content_script_filename_without_extension(self):
        # Filenames without any extension should not be loaded.
        invalid_file_name = 'content_script'
        extension = self.load_extension(
            manifest={
                'content_scripts': [
                    ALWAYS_RUNS_CONTENT_SCRIPT,
                    {
                        'matches': ['<all_urls>'],
                        'js': [invalid_file_name],
                    },
                ],
            },
            files={
                invalid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
                ALWAYS_RUNS_FILE_NAME: SCRIPT_THAT_ALWAYS_RUNS,
            })
        extension.startup()

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.await_message('content-script-loaded')

        self.browser.close_target(content_page)
        extension.unload()

    def test_02_content_script_filename_with_invalid_extension(self):
        valid_file_name = 'content_script.js'
        invalid_file_name = 'content_script.xyz'
        extension = self.load_extension(
            manifest={
                'content_scripts': [
                    ALWAYS_RUNS_CONTENT_SCRIPT,
                    {
                        'matches': ['<all_urls>'],
                        'js': [valid_file_name, invalid_file_name],
                    },
                ],
            },
            files={
                # This makes sure that, when one of the content scripts fails to load,
                # none of the content scripts are executed.
                valid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
                invalid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
                ALWAYS_RUNS_FILE_NAME: SCRIPT_THAT_ALWAYS_RUNS,
            })
        extension.startup()

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.await_message('content-script-loaded')

        self.browser.close_target(content_page)
        extension.unload()

    def test_03_bg_script_injects_script_with_invalid_ext(self):
        background_script = JS('''function backgroundScript() {
    browser.test.sendMessage("background-script-loaded");
  }''')

        valid_file_name = 'background.js'
        invalid_file_name = 'invalid_background.xyz'
        extension = self.load_extension(
            background=JS('''function background() {
      const script = document.createElement("script");
      script.src = "./invalid_background.xyz";
      document.head.appendChild(script);

      const validScript = document.createElement("script");
      validScript.src = "./background.js";
      document.head.appendChild(validScript);
    }'''),
            files={
                invalid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
                valid_file_name: background_script,
            })
        extension.startup()

        extension.await_message('background-script-loaded')

        extension.unload()

    def test_04_background_scripts(self):
        background_script = JS('''function backgroundScript() {
    browser.test.sendMessage("background-script-loaded");
  }''')

        valid_file_name = 'background.js'
        invalid_file_name = 'invalid_background.xyz'
        extension = self.load_extension(
            manifest={
                'background': {
                    'scripts': [invalid_file_name, valid_file_name],
                },
            },
            files={
                invalid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
                valid_file_name: background_script,
            })
        extension.startup()

        extension.await_message('background-script-loaded')

        extension.unload()

    def test_05_background_page_injects_scripts_inline(self):
        injected_background_script = JS('''function injectedBackgroundScript() {
    browser.test.log(
      "inline script injectedBackgroundScript has been executed"
    );
    browser.test.sendMessage("background-script-loaded");
  }''')

        background_html_page = 'background_page.html'
        valid_file_name = 'injected_background.js'
        invalid_file_name = 'invalid_background.xyz'

        inline_script = '''(function () {
    const script = document.createElement("script");
    script.src = "./invalid_background.xyz";
    document.head.appendChild(script);
    const validScript = document.createElement("script");
    validScript.src = "./injected_background.js";
    document.head.appendChild(validScript);
  })()'''

        inline_script_sha256 = compute_sha256_hash(inline_script)

        extension = self.load_extension(
            manifest={
                'background': {'page': background_html_page},
                'content_security_policy': ' '.join([
                    'script-src',
                    "'self'",
                    f"'sha256-{inline_script_sha256}'",
                    ';',
                ]),
            },
            files={
                invalid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
                valid_file_name: injected_background_script,
                'pre-script.js': JS('''() => {
        window.onsecuritypolicyviolation = evt => {
          const { violatedDirective, originalPolicy } = evt;
          browser.test.fail(
            `Unexpected csp violation: ${JSON.stringify({
              violatedDirective,
              originalPolicy,
            })}`
          );
          // Let the test to fail immediately when an unexpected csp violation
          // prevented the inline script from being executed successfully.
          browser.test.sendMessage("background-script-loaded");
        };
      }'''),
                background_html_page: f'''
        <!DOCTYPE html>
        <html>
          <head>
            <meta charset="utf-8"></head>
            <script src="pre-script.js"></script>
            <script>{inline_script}</script>
          </head>
        </html>''',
            })
        extension.startup()

        extension.await_message('background-script-loaded')

        extension.unload()

    def test_06_background_page_injects_scripts(self):
        # This is the initial background script loaded in the HTML page.
        background_script = JS('''function backgroundScript() {
    const script = document.createElement("script");
    script.src = "./invalid_background.xyz";
    document.head.appendChild(script);

    const validScript = document.createElement("script");
    validScript.src = "./injected_background.js";
    document.head.appendChild(validScript);
  }''')

        # This is the script injected by the script defined in `backgroundScript()`.
        injected_background_script = JS('''function injectedBackgroundScript() {
    browser.test.sendMessage("background-script-loaded");
  }''')

        background_html_page = 'background_page.html'
        valid_file_name = 'injected_background.js'
        invalid_file_name = 'invalid_background.xyz'
        extension = self.load_extension(
            manifest={
                'background': {'page': background_html_page},
            },
            files={
                invalid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
                valid_file_name: injected_background_script,
                background_html_page: '''
        <html>
          <head>
            <meta charset="utf-8"></head>
            <script src="./background.js"></script>
          </head>
        </html>''',
                'background.js': background_script,
            })
        extension.startup()

        extension.await_message('background-script-loaded')

        extension.unload()

    def test_07_background_script_registers_content_script(self):
        invalid_file_name = 'content_script'
        extension = self.load_extension(
            manifest={
                'permissions': ['<all_urls>'],
            },
            background=JS('''async function background() {
      await browser.contentScripts.register({
        js: [{ file: "/content_script" }],
        matches: ["<all_urls>"],
      });
      browser.test.sendMessage("background-script-loaded");
    }'''),
            files={
                invalid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
            })
        extension.startup()

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.await_message('background-script-loaded')

        self.browser.close_target(content_page)
        extension.unload()

    def test_08_web_accessible_resources(self):
        content_script = JS('''function contentScript() {
    const script = document.createElement("script");
    script.src = browser.runtime.getURL("content_script.css");
    script.onerror = () => {
      browser.test.sendMessage("second-content-script-loaded");
    };

    document.head.appendChild(script);
  }''')

        content_script_file_name = 'content_script.js'
        invalid_file_name = 'content_script.css'
        extension = self.load_extension(
            manifest={
                'web_accessible_resources': [invalid_file_name],
                'content_scripts': [
                    ALWAYS_RUNS_CONTENT_SCRIPT,
                    {
                        'matches': ['<all_urls>'],
                        'js': [content_script_file_name],
                    },
                ],
            },
            files={
                invalid_file_name: SCRIPT_THAT_SHOULD_NOT_BE_LOADED,
                content_script_file_name: content_script,
                ALWAYS_RUNS_FILE_NAME: SCRIPT_THAT_ALWAYS_RUNS,
            })
        extension.startup()

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.await_message('content-script-loaded')
        extension.await_message('second-content-script-loaded')

        self.browser.close_target(content_page)
        extension.unload()
