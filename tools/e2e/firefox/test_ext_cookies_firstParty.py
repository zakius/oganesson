"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_cookies_firstParty.js.

The add-ons' code is Firefox's, as it is. Firefox's prefs, in this browser's
form:

- network.cookie.cookieBehavior 0, every cookie allowed: the setting that
  allows third-party cookies, which this browser blocks by default.
- network.cookie.sameSite.laxByDefault on: as Chromium always does.
- network.cookie.sameSite.noneRequiresSecure off, so that the test server's
  SameSite=None cookie, which isn't Secure, is taken: Chromium always refuses
  one, and Firefox's test turns the rule off only because its server has no
  HTTPS. Here the server's SameSite=None cookie is Secure, and the test's hosts
  count as secure (--unsafely-treat-insecure-origin-as-secure), so that the
  cookie is set and sent as in Firefox's test.

The server's handlers are Firefox's: the cookies a load sends are those that
reach /checkCookies or /navigate last before /ready. Firefox's echocookies
handler for an add-on's background allows the add-on's origin, which it knows
before the add-on starts; here it allows the request's own Origin when that is
an add-on's."""

from extension_test_utils import JS, FirefoxTest
from harness import wait_for

HTML = {'Content-Type': 'text/html; charset=utf-8'}
HOSTS = ('example.org', 'example.net', 'example.com')


def page(body):
    return (200, HTML, body.encode())


def echo_cookies(headers):
    return (200, HTML, headers.get('Cookie', '').encode())


def echo_cookies_to_add_on(headers):
    origin = headers.get('Origin', '')
    allow = {'Access-Control-Allow-Origin': origin,
             'Access-Control-Allow-Credentials': 'true'} if origin.startswith('chrome-extension://') else {}
    return (200, {**HTML, **allow}, headers.get('Cookie', '').encode())


ROUTES = {
    '/setCookies': (200, {**HTML, 'Set-Cookie': ['none=a; sameSite=none; Secure',
                                                 'lax=b; sameSite=lax',
                                                 'strict=c; sameSite=strict']},
                    b'<html></html>'),
    '/checkCookies': (302, {**HTML, 'Location': '/ready'}, b''),
    '/navigate': page("<html><script>location = '/checkCookies';</script></html>"),
    # /checkCookies ultimately redirects to /ready, which resolves the
    # promise returned by promiseLoadedCookies(). At that point, the test
    # can choose to close the ContentPage that hosts us, and abort the
    # pending fetch(). When extensions.webextensions.remote is false, the
    # PromiseTestUtils.assertNoUncaughtRejections() check may detect this
    # and cause the test to fail unexpectedly. To avoid this issue, we catch
    # the error unconditionally.
    '/fetch': page("""<html><script>
        fetch("/checkCookies").catch(e => console.log("fetch() error: " + e));
      </script></html>"""),
    '/nestedfetch': page("<html><iframe src='http://example.net/nestedfetch2'></iframe></html>"),
    '/nestedfetch2': page("<html><iframe src='http://example.org/fetch'></iframe></html>"),
    '/ready': page('<html></html>'),
    '/contentScriptHere': page('<html></html>'),
    '/pageWithFrames': page("""
      <html>
        <iframe src="http://example.com/contentScriptHere"></iframe>
        <iframe src="http://example.net/contentScriptHere"></iframe>
      </html>
    """),
    '/empty': page('<html><body></body></html>'),
}

PAGE_SCRIPT = JS(r'''async function pageScript() {
  const ifr = document.createElement("iframe");
  ifr.src = "http://example.org/" + location.search.slice(1);
  document.body.appendChild(ifr);
}''')

IFRAMES_CONTENT_SCRIPT = JS(r'''async () => {
  const res = await fetch("http://example.org/echocookies");
  const cookies = await res.text();
  browser.test.assertEq(
    "none=a",
    cookies,
    "expected cookies in content script"
  );
  browser.test.sendMessage("extfetch:" + location.hostname);
}''')

BACKGROUND_FETCH = JS(r'''async function background() {
  const res = await fetch("http://example.org/echocookies", {
    credentials: "include",
  });
  const cookies = await res.text();
  browser.test.sendMessage("fetchcookies", cookies);
}''')

CONTENT_SCRIPT_FETCH = JS(r'''async function contentScript() {
  let res = await fetch("http://example.org/checkCookies");
  browser.test.assertEq(location.origin + "/ready", res.url, "request OK");
  browser.test.sendMessage("fetch-done");
}''')


class CookiesFirstPartyTest(FirefoxTest):
    hosts = HOSTS
    routes = dict(ROUTES)
    prefs = {'profile': {'cookie_controls_mode': 0}}
    browser_args = (*FirefoxTest.browser_args, '--unsafely-treat-insecure-origin-as-secure='
                    + ','.join(f'http://{host}' for host in HOSTS))

    def setUp(self):
        super().setUp()
        self.routes['/echocookies'] = echo_cookies

    def promise_loaded_cookies(self, start):
        """promiseLoadedCookies(): the cookies that the load since request
        `start` sent, once it reaches /ready."""
        requests = self.server.requests
        wait_for(lambda: '/ready' in requests[start:], what='/ready')
        ready = start + requests[start:].index('/ready')
        last = max(i for i in range(start, ready) if requests[i] in ('/checkCookies', '/navigate'))
        return self.server.headers[requests[last]].get('Cookie', '')

    def load_and_check(self, url, expected):
        start = len(self.server.requests)
        tab = self.open_tab(url)
        # Let's check the cookies received during the last loading.
        self.is_(self.promise_loaded_cookies(start), expected, f'cookies sent from {url}')
        self.browser.close_target(tab)

    def test_01_setup(self):
        # Let's set 3 cookies before loading the extension.
        tab = self.open_tab('http://example.org/setCookies')
        self.browser.close_target(tab)
        self.is_(len(self.browser.browser_call('Storage.getCookies')['cookies']), 3,
                 'Services.cookies.cookies.length')

    def test_02_cookies_firstParty(self):
        extension = self.load_extension(
            manifest={'permissions': ['*://example.org/']},
            files={
                'page.html': '<body><script src="page.js"></script></body>',
                'page.js': PAGE_SCRIPT,
            })
        extension.startup()

        # This page will load example.org in an iframe.
        url = f'chrome-extension://{extension.id}/page.html'
        self.load_and_check(url + '?checkCookies', 'none=a; lax=b; strict=c')
        # Let's navigate.
        self.load_and_check(url + '?navigate', 'none=a; lax=b; strict=c')
        # Let's run a fetch()
        self.load_and_check(url + '?fetch', 'none=a; lax=b; strict=c')
        # Let's run a fetch() from a nested iframe (extension -> example.net ->
        # example.org -> fetch)
        self.load_and_check(url + '?nestedfetch', 'none=a')
        # Let's run a fetch() from a nested iframe (extension -> example.org -> fetch)
        self.load_and_check(url + '?nestedfetch2', 'none=a; lax=b; strict=c')
        extension.unload()

    def test_03_cookies_iframes(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['*://example.org/'],
                'content_scripts': [{
                    'js': ['contentScript.js'],
                    'matches': [
                        '*://example.com/contentScriptHere',
                        '*://example.net/contentScriptHere',
                    ],
                    'run_at': 'document_end',
                    'all_frames': True,
                }],
            },
            files={'contentScript.js': IFRAMES_CONTENT_SCRIPT})
        extension.startup()
        tab = self.open_tab('http://example.com/pageWithFrames')
        extension.await_message('extfetch:example.com')
        extension.await_message('extfetch:example.net')
        self.browser.close_target(tab)
        extension.unload()

    def test_04_cookies_background(self):
        self.routes['/echocookies'] = echo_cookies_to_add_on
        tests = [
            {'permissions': ['http://example.org/*'], 'cookies': 'none=a; lax=b; strict=c'},
            {'permissions': [], 'cookies': 'none=a'},
        ]
        for test in tests:
            extension = self.load_extension(background=BACKGROUND_FETCH,
                                            manifest={'permissions': test['permissions']})
            extension.startup()
            self.is_(extension.await_message('fetchcookies'), test['cookies'],
                     'extension with permissions can see SameSite-restricted cookies')
            extension.unload()

    def test_05_cookies_contentScript(self):
        extension = self.load_extension(
            manifest={
                'content_scripts': [{
                    'run_at': 'document_end',
                    'js': ['contentscript.js'],
                    'matches': ['*://*/*'],
                }],
            },
            files={'contentscript.js': CONTENT_SCRIPT_FETCH})
        extension.startup()
        start = len(self.server.requests)
        tab = self.open_tab('http://example.org/empty')
        extension.await_message('fetch-done')
        # Let's check the cookies received during the last loading.
        self.is_(self.promise_loaded_cookies(start), 'none=a; lax=b; strict=c',
                 'cookies sent from the content script')
        self.browser.close_target(tab)
        extension.unload()
