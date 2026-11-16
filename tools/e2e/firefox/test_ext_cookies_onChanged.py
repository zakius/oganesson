"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_cookies_onChanged.js.

The add-ons' code is Firefox's, as it is. The test adds and removes a cookie
with Gecko's cookie service; here DevTools does that in a tab's own cookie
store (Network.setCookie and Network.deleteCookies): a tab of a private window
for a private cookie. Left out: the checks that the event pages' listeners are
primed (Gecko's assertPersistentListeners()). The port checks instead that the
non-private add-on's event page stays stopped after the private cookie's
change; the private one's events show that its page woke.
terminateBackground() needs EVENT_PAGE_ARGS."""

import time

from extension_test_utils import EVENT_PAGE_ARGS, JS, FirefoxTest
from harness import Page, wait_for

BACKGROUND = JS(r'''function background() {
  browser.cookies.onChanged.addListener(changeInfo => {
    browser.test.sendMessage("cookie-event", changeInfo);
  });
}''')


class CookiesOnChangedTest(FirefoxTest):
    browser_args = (*FirefoxTest.browser_args, *EVENT_PAGE_ARGS)

    def create_test_extension(self, private_allowed):
        return self.load_extension(
            incognito_override='spanning' if private_allowed else None,
            manifest={
                'permissions': ['cookies'],
                'host_permissions': ['https://example.com/'],
                'background': {'persistent': False},
            },
            background=BACKGROUND)

    def private_tab(self):
        """A tab of a new private window."""
        before = {t['id'] for t in self.browser.targets()}
        self.browser.key('ctrl+shift+n')
        return Page(wait_for(lambda: next((t for t in self.browser.targets()
                                           if t['id'] not in before and t['type'] == 'page'),
                                          None), what='the private window'))

    def add_and_remove_cookie(self, is_private):
        cookie = {
            'name': 'cookname',
            'value': 'cookvalue',
            'domain': 'example.com',
            'hostOnly': True,
            'path': '/',
            'secure': True,
            'httpOnly': False,
            'sameSite': 'lax',
            'session': False,
            'firstPartyDomain': '',
            'partitionKey': None,
            'expirationDate': int(time.time()) + 3600,
            'storeId': 'firefox-private' if is_private else 'firefox-default',
        }
        page = self.private_tab() if is_private else self.open_tab('about:blank')
        try:
            page.call('Network.setCookie', name=cookie['name'], value=cookie['value'],
                      url='https://example.com/', path=cookie['path'], secure=True,
                      httpOnly=False, sameSite='Lax', expires=cookie['expirationDate'])
            page.call('Network.deleteCookies', name=cookie['name'], url='https://example.com/',
                      path=cookie['path'])
        finally:
            self.browser.close_target(page)
        return cookie

    def background_running(self, extension):
        prefix = f'chrome-extension://{extension.id}/'
        return any(t['url'].startswith(prefix) and t['type'] == 'background_page'
                   for t in self.browser.targets())

    def deep_equal(self, actual, expected, message):
        """Assert.deepEqual()."""
        self.check(actual == expected, f'{message} - Expected: {expected}, Actual: {actual}')

    def test_01_onChanged_event_page(self):
        non_private = self.create_test_extension(private_allowed=False)
        private = self.create_test_extension(private_allowed=True)
        private.startup()
        non_private.startup()

        # Suspend both event pages.
        private.terminate_background()
        non_private.terminate_background()

        # Modifying a private cookie should wake up the private extension, but not
        # the other one that does not have access to private browsing data.
        private_cookie = self.add_and_remove_cookie(is_private=True)
        self.deep_equal(private.await_message('cookie-event'),
                        {'removed': False, 'cookie': private_cookie, 'cause': 'explicit'},
                        'cookies.onChanged for private cookie creation')
        self.deep_equal(private.await_message('cookie-event'),
                        {'removed': True, 'cookie': private_cookie, 'cause': 'explicit'},
                        'cookies.onChanged for private cookie removal')
        # ... but the non-private extension should still be sound asleep.
        self.check(not self.background_running(non_private),
                   'the non-private event page stays asleep')

        # A non-private cookie modification should notify both extensions.
        cookie = self.add_and_remove_cookie(is_private=False)
        self.deep_equal(private.await_message('cookie-event'),
                        {'removed': False, 'cookie': cookie, 'cause': 'explicit'},
                        'cookies.onChanged for cookie creation in privateExtension')
        self.deep_equal(private.await_message('cookie-event'),
                        {'removed': True, 'cookie': cookie, 'cause': 'explicit'},
                        'cookies.onChanged for cookie removal in privateExtension')
        self.deep_equal(non_private.await_message('cookie-event'),
                        {'removed': False, 'cookie': cookie, 'cause': 'explicit'},
                        'cookies.onChanged for cookie creation in nonPrivateExtension')
        self.deep_equal(non_private.await_message('cookie-event'),
                        {'removed': True, 'cookie': cookie, 'cause': 'explicit'},
                        'cookies.onChanged for cookie removal in nonPrivateCookie')

        private.unload()
        non_private.unload()
