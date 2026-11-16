"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_browserSettings_homepage.js.

Firefox's home page is the pref browser.startup.homepage; this browser's is
the profile's `homepage`, when `homepage_is_newtabpage` is off. The test sets
both, and expects the home page it set."""

from extension_test_utils import JS, FirefoxTest

HOMEPAGE = 'https://example.org/start'


class BrowserSettingsHomepageTest(FirefoxTest):
    prefs = {'homepage': HOMEPAGE, 'homepage_is_newtabpage': False}

    def test_01_homepage_get_without_set(self):
        background = JS('''async function background() {
            let homepage = await browser.browserSettings.homepageOverride.get({});
            browser.test.sendMessage("homepage", homepage);
          }''')

        extension = self.load_extension(
            background=background,
            manifest={
                'permissions': ['browserSettings'],
            })

        default_homepage = HOMEPAGE

        extension.startup()
        homepage = extension.await_message('homepage')
        self.assertEqual(homepage['value'], default_homepage,
                         'The homepageOverride setting has the expected value.')
        self.assertEqual(homepage['levelOfControl'], 'not_controllable',
                         'The homepageOverride setting has the expected levelOfControl.')

        extension.unload()
