"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_proxy_failover.js.

The add-ons' code is Firefox's, as it is. Firefox proxies its localhost
server with network.proxy.allow_hijacking_localhost; this browser never
proxies a loopback host, so the server is example.com here. The fetch
error is this browser's own message. test_failover_pac's add-on sets
proxy.settings, and the check of Firefox's network.proxy prefs reads this
browser's proxy pref, which says the same. Left out, as Gecko internals: the
failover of the browser's own requests (xpcshell's system-principal XHR and
ServiceRequest, in test_failover_system, test_failover_pac's request,
test_failover_system_off and its network.proxy.failover_direct pref), and a
channel's bypassProxy flag (both test_bypass_proxy tasks)."""

import json
import socket

from extension_test_utils import JS
from firefox.head_proxy import ProxyTest

HOST = 'example.com'


def get_bad_proxy_port():
    """A free port with no listener, for the proxy info."""
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        return server.getsockname()[1]


class ProxyFailoverTest(ProxyTest):
    hosts = (HOST,)
    routes = {'/': (200, {'Content-Type': 'text/plain'}, b'ok!')}

    def get_proxy_extension(self, proxy_details):
        extension = self.load_extension(
            manifest={'permissions': ['proxy', '<all_urls>']},
            background=JS(r'''async function background(proxyDetails) {
    browser.proxy.onRequest.addListener(
      () => {
        return proxyDetails;
      },
      { urls: ["<all_urls>"] }
    );

    browser.test.sendMessage("proxied");
  }''', json.dumps(proxy_details)),
            incognito_override='spanning')
        extension.startup()
        extension.await_message('proxied')
        return extension

    def fetch(self, page, url):
        """ExtensionTestUtils.fetch() from `page`: the text, or the error's
        message."""
        return page.eval(f'fetch({json.dumps(url)}).then(r => r.text(), e => ({{error: e.message}}))')

    def test_01_failover_content_direct(self):
        # load a content page for fetch and non-system principal, expect
        # failover to direct will work.
        proxy_details = [
            {'type': 'http', 'host': '127.0.0.1', 'port': get_bad_proxy_port()},
            {'type': 'direct'},
        ]

        # We need to load the content page before loading the proxy extension
        # to ensure that we have a valid content page to run fetch from.
        content_url = f'http://{HOST}:{self.server.port}/'
        page = self.open_tab(content_url)

        extension = self.get_proxy_extension(proxy_details)

        text = self.fetch(page, f'{content_url}?t=1')
        self.equal(text, 'ok!', 'fetch completed')

        extension.unload()
        self.browser.close_target(page)

    def test_02_failover_content(self):
        # load a content page for fetch and non-system principal, expect
        # no failover
        proxy_details = [
            {'type': 'http', 'host': '127.0.0.1', 'port': get_bad_proxy_port()},
        ]

        content_url = f'http://{HOST}:{self.server.port}/'
        page = self.open_tab(content_url)

        extension = self.get_proxy_extension(proxy_details)

        result = self.fetch(page, f'{content_url}?t=2')
        if isinstance(result, dict):
            self.equal(result['error'], 'Failed to fetch', 'fetch failed')
        else:
            self.ok(False, 'xhr unexpectedly completed')

        extension.unload()
        self.browser.close_target(page)

    def test_03_failover_pac(self):
        bad_port = get_bad_proxy_port()

        extension = self.load_extension(
            manifest={'permissions': ['proxy', '<all_urls>']},
            background=JS(r'''async function background(badPort) {
      let pac = `function FindProxyForURL(url, host) { return "PROXY 127.0.0.1:${badPort}"; }`;
      let proxySettings = {
        proxyType: "autoConfig",
        autoConfigUrl: `data:application/x-ns-proxy-autoconfig;charset=utf-8,${encodeURIComponent(
          pac
        )}`,
      };

      await browser.proxy.settings.set({ value: proxySettings });
      browser.test.sendMessage("proxied");
    }''', str(bad_port)),
            incognito_override='spanning')
        extension.startup()
        extension.await_message('proxied')
        # Firefox's network.proxy.type 2 and network.proxy.autoconfig_url:
        # this browser's proxy pref.
        proxy = self.browser.profile_prefs().get('proxy', {})
        self.equal(proxy.get('mode'), 'pac_script', 'autoconfig type set')
        self.ok(proxy.get('pac_url'), 'autoconfig url set')

        extension.unload()
