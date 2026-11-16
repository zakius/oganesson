"""Firefox's toolkit/components/extensions/test/mochitest/head_cookies.js, for
the ports of the cookies mochitests, and Gecko's cookie service in the form
this browser has: DevTools' Network and Storage domains on the default store.

testCookies() keeps its add-on's code as Firefox has it. Firefox's tests set
network.cookie.quotaPerHost and maxPerHost to 3, so that the fourth cookie of
a host evicts one; Chromium's limit is fixed (180 cookies a host, purged to
150), so no cookie is evicted here. The checks of that eviction fail: the
add-on's "got no eviction event", and the test's own count of a host's
cookies at the end, which still has the cookie Firefox evicts."""

import json
import time

from extension_test_utils import JS

# SCHEME_HTTP and SCHEME_HTTPS of Gecko's cookie service, in DevTools' form.
SCHEMES = {False: 'NonSecure', True: 'Secure'}


class CookieService:
    """Services.cookies, through a tab of its own (`page`, a private window's
    tab for the private store)."""

    def __init__(self, page):
        self.page = page

    def add(self, host, path, name, value, secure, http_only, session, expiry_ms,
            https=False):
        """Services.cookies.add(host, path, name, value, isSecure, isHttpOnly,
        isSession, expiry, {}, SAMESITE_UNSET, scheme). A host with a leading
        dot is a domain cookie's."""
        # Chromium refuses a Secure cookie from an insecure scheme, which
        # Gecko's service takes: such a cookie comes from a secure one here.
        params = {'name': name, 'value': value, 'domain': host, 'path': path,
                  'secure': secure, 'httpOnly': http_only,
                  'sourceScheme': SCHEMES[https or secure]}
        if not session:
            params['expires'] = expiry_ms / 1000
        self.page.call('Network.setCookie', **params)

    def remove(self, host, name, path):
        """Services.cookies.remove(host, name, path, {})."""
        self.page.call('Network.deleteCookies', name=name, domain=host, path=path)


def cookies_from_host(test, host):
    """Services.cookies.getCookiesFromHost(host, {}): the default store's
    cookies of the host's base domain, which Gecko keeps them under."""
    base = '.'.join(host.strip('.').split('.')[-2:])
    return [c for c in test.browser.browser_call('Storage.getCookies')['cookies']
            if c['domain'].lstrip('.') == base or c['domain'].endswith('.' + base)]


def test_cookies(test, options):
    """testCookies(options): an add-on with options['permissions'] reads,
    writes and removes the cookies of options['url'] and options['domain'],
    while the test changes them."""
    # Changing the options object is a bit of a hack, but it allows us to easily
    # pass an expiration date to the background script.
    options = {**options, 'expiry': time.time() + 3600}

    background = JS(r'''async function background(backgroundOptions) {
    // Ask the parent scope to change some cookies we may or may not have
    // permission for.
    let awaitChanges = new Promise(resolve => {
      browser.test.onMessage.addListener(msg => {
        browser.test.assertEq("cookies-changed", msg, "browser.test.onMessage");
        resolve();
      });
    });

    let changed = [];
    browser.cookies.onChanged.addListener(event => {
      changed.push(`${event.cookie.name}:${event.cause}`);
    });
    browser.test.sendMessage("change-cookies");

    // Try to access some cookies in various ways.
    let { url, domain, secure } = backgroundOptions;

    let failures = 0;
    let tallyFailure = () => {
      failures++;
    };

    try {
      await awaitChanges;

      let cookie = await browser.cookies.get({ url, name: "foo" });
      browser.test.assertEq(
        backgroundOptions.shouldPass,
        cookie != null,
        "should pass == get cookie"
      );

      let cookies = await browser.cookies.getAll({ domain });
      if (backgroundOptions.shouldPass) {
        browser.test.assertEq(2, cookies.length, "expected number of cookies");
      } else {
        browser.test.assertEq(0, cookies.length, "expected number of cookies");
      }

      await Promise.all([
        browser.cookies
          .set({
            url,
            domain,
            secure,
            name: "foo",
            value: "baz",
            expirationDate: backgroundOptions.expiry,
          })
          .catch(tallyFailure),
        browser.cookies
          .set({
            url,
            domain,
            secure,
            name: "bar",
            value: "quux",
            expirationDate: backgroundOptions.expiry,
          })
          .catch(tallyFailure),
        browser.cookies.remove({ url, name: "deleted" }),
      ]);

      if (backgroundOptions.shouldPass) {
        // The order of eviction events isn't guaranteed, so just check that
        // it's there somewhere.
        let evicted = changed.indexOf("evicted:evicted");
        if (evicted < 0) {
          browser.test.fail("got no eviction event");
        } else {
          browser.test.succeed("got eviction event");
          changed.splice(evicted, 1);
        }

        browser.test.assertEq(
          "x:explicit,x:overwrite,x:explicit,x:explicit,foo:overwrite,foo:explicit,bar:explicit,deleted:explicit",
          changed.join(","),
          "expected changes"
        );
      } else {
        browser.test.assertEq("", changed.join(","), "expected no changes");
      }

      if (!(backgroundOptions.shouldPass || backgroundOptions.shouldWrite)) {
        browser.test.assertEq(2, failures, "Expected failures");
      } else {
        browser.test.assertEq(0, failures, "Expected no failures");
      }

      browser.test.notifyPass("cookie-permissions");
    } catch (error) {
      browser.test.fail(`Error: ${error} :: ${error.stack}`);
      browser.test.notifyFail("cookie-permissions");
    }
  }''', json.dumps(options))

    extension = test.load_extension(manifest={'permissions': options['permissions']},
                                    background=background)

    page = test.open_tab('about:blank')
    try:
        cookies = CookieService(page)
        domain = '.' + options['domain'].lstrip('.')
        https = options['url'].startswith('https')

        def add(name, value):
            cookies.add(domain, '/', name, value, options['secure'], False, False,
                        options['expiry'] * 1000, https)

        # This will be evicted after we add a fourth cookie.
        add('evicted', 'bar')
        # This will be modified by the background script
        add('foo', 'bar')
        # This will be deleted by the background script.
        add('deleted', 'bar')

        extension.startup()

        extension.await_message('change-cookies')

        # this is the fourth cookie, it triggers a purge
        add('x', 'y')
        # overwrite the latest cookie
        add('x', 'z')
        cookies.remove(domain, 'x', '/')

        extension.send_message('cookies-changed')

        extension.await_finish('cookie-permissions')
        extension.unload()

        found = sorted(cookies_from_host(test, options['domain']), key=lambda c: c['name'])
        names = [(c['name'], c['value']) for c in found]
        if options['shouldPass']:
            test.is_(names, [('bar', 'quux'), ('foo', 'baz')], 'expected two cookies for host')
        elif options.get('shouldWrite'):
            # Note: |shouldWrite| applies only when |shouldPass| is false.
            # This is necessary because, unfortunately, websites (and therefore web
            # extensions) are allowed to write some cookies which they're not allowed
            # to read.
            test.is_(names, [('bar', 'quux'), ('deleted', 'bar'), ('foo', 'baz')],
                     'expected three cookies for host')
        else:
            test.is_(names, [('deleted', 'bar'), ('foo', 'bar')], 'expected two cookies for host')

        for cookie in found:
            cookies.remove(cookie['domain'], cookie['name'], '/')
        # Make sure we don't silently poison subsequent tests if something goes wrong.
        test.is_(cookies_from_host(test, options['domain']), [], 'cookies cleared')
    finally:
        test.browser.close_target(page)
