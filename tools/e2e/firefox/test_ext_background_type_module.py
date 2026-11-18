"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_background_type_module.js.

Firefox's generated background page is Chromium's
_generated_background_page.html: the port reads its scripts in the running
background page, where Firefox loads the page again in a content page. Each
script's URL is its resolved `src`, as in Firefox's page. A script without a
`type` attribute is JavaScript, as HTML says, so the port takes it for
Firefox's `text/javascript`. The harness's own script (the test API), which it
adds first to every background, is left out. Firefox's manifest error is the
browser's refusal to load the add-on, with Firefox's text.
"""

from extension_test_utils import TEST_API_FILE, FirefoxTest
from harness import Page

# The generated page's scripts, as {URL: type}.
SCRIPT_TYPES = '''Object.fromEntries(Array.from(document.querySelectorAll("script"),
  script => [script.src, script.getAttribute("type") || "text/javascript"]))'''


class BackgroundTypeModuleTest(FirefoxTest):

    def assert_background_script_types(self, extension, expected):
        base = f'chrome-extension://{extension.id}/'
        page = Page(next(t for t in self.browser.targets()
                         if t['url'] == f'{base}_generated_background_page.html'))
        try:
            types = page.eval(SCRIPT_TYPES, gesture=False)
        finally:
            page.close()
        types.pop(base + TEST_API_FILE, None)
        self.assertEqual(types, {base + path: kind for path, kind in expected.items()},
                         'Got the expected script type from the generated background page')

    def background_script_classic(self, manifest_type_classic_set):
        background = {'scripts': ['anotherScript.js', 'main.js']}
        if manifest_type_classic_set:
            background['type'] = 'classic'
        extension = self.load_extension(
            manifest={'background': background},
            files={'main.js': '', 'anotherScript.js': ''})

        extension.startup()
        self.assert_background_script_types(extension, {
            'main.js': 'text/javascript',
            'anotherScript.js': 'text/javascript',
        })
        extension.unload()

    def test_01_background_scripts_type_default(self):
        self.background_script_classic(manifest_type_classic_set=False)

    def test_02_background_scripts_type_classic(self):
        self.background_script_classic(manifest_type_classic_set=True)

    def test_03_background_scripts_type_module(self):
        extension = self.load_extension(
            manifest={
                'background': {
                    'scripts': ['anotherModule.js', 'mainModule.js'],
                    'type': 'module',
                },
            },
            files={
                'mainModule.js': '''
                  import { initBackground } from "/importedModule.js";
                  browser.test.log("mainModule.js - ESM module executing");
                  initBackground();
                ''',
                'importedModule.js': '''
                  export function initBackground() {
                    browser.test.onMessage.addListener((msg) => {
                      browser.test.log("importedModule.js - test message received");
                      browser.test.sendMessage("esm-module-reply", msg);
                    });
                    browser.test.log("importedModule.js - initBackground executed");
                  }
                  browser.test.log("importedModule.js - ESM module loaded");
                ''',
                'anotherModule.js': '''
                  browser.test.log("anotherModule.js - ESM module loaded");
                ''',
            })

        extension.startup()
        extension.send_message('test-event-value')
        self.assertEqual(
            extension.await_message('esm-module-reply'), 'test-event-value',
            'Got the expected event from the ESM module loaded from the background script')
        self.assert_background_script_types(extension, {
            'mainModule.js': 'module',
            'anotherModule.js': 'module',
        })
        extension.unload()

    def test_04_background_scripts_type_invalid(self):
        extension = self.load_extension(
            manifest={
                'background': {
                    'scripts': ['anotherScript.js', 'main.js'],
                    'type': 'invalid',
                },
            },
            files={'main.js': '', 'anotherScript.js': ''})

        with self.assertRaisesRegex(
                RuntimeError,
                'Error processing background.type: Invalid enumeration value "invalid"',
                msg='Expected install to fail'):
            extension.startup()
