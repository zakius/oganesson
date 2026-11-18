"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_i18n_system.js.

The add-on's code is Firefox's, as it is. Firefox's test expects the system's
locales, which it reads from Gecko's OS preferences (mozIOSPreferences): on
Linux, the locale of the environment. Here that is the browser's environment:
LC_ALL, else LANG (the harness passes on no other), as a BCP 47 tag, or
`en-US` when neither is set.

As in Firefox, the content page loads before the add-on starts, and Firefox
runs the add-on's content script in it: the port opens it at the same point."""

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


def system_locales(env):
    """The environment's locale as Gecko's OS preferences give it."""
    value = env.get('LC_ALL') or env.get('LANG') or ''
    # en_US.UTF-8@euro -> en-US
    tag = value.split('.')[0].split('@')[0].replace('_', '-')
    return [tag] if tag and tag not in ('C', 'POSIX') else ['en-US']


class I18nSystemTest(FirefoxTest):
    routes = {'/data/file_sample.html': (200, HTML, FILE_SAMPLE)}

    def setUp(self):
        super().setUp()
        self.base_url = self.server.url('/data', host='localhost')

    def test_01_get_preferred_system_languages(self):
        extension = self.load_extension(
            manifest={
                'content_scripts': [
                    {
                        'matches': ['http://*/*/file_sample.html'],
                        'run_at': 'document_start',
                        'js': ['content_script.js'],
                    },
                ],
            },

            background=JS(r'''function background() {
    browser.test.onMessage.addListener((msg, expected) => {
      browser.test.assertEq("expect-results", msg, "Expected message");
      browser.i18n.getPreferredSystemLanguages().then(results => {
        browser.test.assertDeepEq(
          expected,
          results,
          "got expected languages in background"
        );

        const isNonEmptyArray = Array.isArray(results) && !!results.length;
        browser.test.assertTrue(isNonEmptyArray, "Is non empty array");

        const canonicalLocales = Intl.getCanonicalLocales(results);
        browser.test.assertDeepEq(
          results,
          canonicalLocales,
          "Result gives canonical versions"
        );

        browser.test.sendMessage("background-done");
      });
    });
  }'''),

            files={
                'content_script.js': JS(r'''function content() {
    browser.test.onMessage.addListener((msg, expected) => {
      browser.test.assertEq("expect-results", msg, "Expected message");
      browser.i18n.getPreferredSystemLanguages().then(results => {
        browser.test.assertDeepEq(
          expected,
          results,
          "got expected languages in contentScript"
        );

        browser.test.sendMessage("content-done");
      });
    });
    browser.test.sendMessage("content-loaded");
  }'''),
            })

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.startup()
        extension.await_message('content-loaded')

        locales_without_overwriting_preferences = system_locales(self.browser.env())

        extension.send_message('expect-results', locales_without_overwriting_preferences)

        extension.await_message('background-done')
        extension.await_message('content-done')

        self.browser.close_target(content_page)

        extension.unload()
