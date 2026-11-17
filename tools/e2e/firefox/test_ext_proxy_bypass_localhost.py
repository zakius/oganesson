"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_proxy_bypass_localhost.js.

The add-on's code is Firefox's, as it is. Its proxy is head_proxy's
ProxyServer, and Firefox's DNS override of example.com is a host rule. The
pages declare no favicon, so that a tab requests nothing more, as Firefox's
content page doesn't. Firefox's network.proxy.no_proxies_on, its proxy
settings' exceptions, is the bypass list of this browser's proxy pref (a
fixed proxy that nothing reaches), which the browser reads at its start: that
part of Firefox's task is test_02, in a browser of its own. Left out: the
checks with network.proxy.allow_hijacking_localhost on, a Gecko pref that
lets add-ons proxy localhost, which this browser never does (its default is
Firefox's)."""

import socket

from extension_test_utils import JS
from firefox.head_proxy import ProxyServer, ProxyTest

# A page that asks for no favicon.
PAGE = (200, {'Content-Type': 'text/html'}, b'<!DOCTYPE html><link rel="icon" href="data:,">')

BACKGROUND = r'''function background(port) {
    browser.webRequest.onCompleted.addListener(
      details => {
        browser.test.log(`onCompleted ${JSON.stringify(details)}\n`);

        if (details.proxyInfo) {
          browser.test.assertEq(
            "localhost",
            details.proxyInfo.host,
            "proxy host"
          );
          browser.test.assertEq(port, details.proxyInfo.port, "proxy port");
          browser.test.assertEq("http", details.proxyInfo.type, "proxy type");
        }

        browser.test.sendMessage(
          "requestCompleted",
          details.proxyInfo ? "proxied" : "not_proxied"
        );
      },
      { urls: ["<all_urls>"] }
    );

    // Handle the proxy request.
    browser.proxy.onRequest.addListener(
      details => {
        browser.test.log(`onRequest ${JSON.stringify(details)}`);
        return [
          {
            host: "localhost",
            port,
            type: "http",
          },
        ];
      },
      { urls: ["<all_urls>"] },
      ["requestHeaders"]
    );
  }'''


class ProxyBypassBase(ProxyTest):
    hosts = ('example.com',)
    routes = {'/': PAGE}

    @classmethod
    def setUpClass(cls):
        cls.proxy = ProxyServer(answer=PAGE)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.proxy.stop()

    def server_count(self):
        return self.server.requests.count('/')

    def proxy_count(self):
        return sum(1 for request in self.proxy.requests if request[0] == 'http')

    def get_extension(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['proxy', 'webRequest', 'webRequestBlocking', '<all_urls>'],
                'host_permissions': [
                    f'http://localhost:{self.server.port}/*',
                    'http://localhost/*',
                ],
            },
            background=JS(BACKGROUND, str(self.proxy.port)))
        extension.startup()
        return extension

    def check_page(self, extension, url, completed, proxied, message):
        """Loads `url` in a tab (loadContentPage()), and checks the add-on's
        requestCompleted and the requests the proxy and the server got."""
        proxy_count = self.proxy_count()
        server_count = self.server_count()
        content_page = self.browser.new_tab(url)
        self.equal(extension.await_message('requestCompleted'), completed, 'requestCompleted')
        if proxied:
            self.equal(self.proxy_count(), proxy_count + 1, message)
            self.equal(self.server_count(), server_count, 'No extra direct requests')
        else:
            self.equal(self.proxy_count(), proxy_count, "Shouldn't see any proxy requests")
            self.equal(self.server_count(), server_count + 1, message)
        self.browser.close_target(content_page)


class ProxyBypassLocalhostTest(ProxyBypassBase):

    def test_01_webRequest_auth_proxy(self):
        extension = self.get_extension()

        # The request doesn't allow the webextension to force the proxying of
        # a localhost request.
        self.check_page(extension, f'http://localhost:{self.server.port}/', 'not_proxied',
                        False, 'Should have one extra server request')

        # Make sure unproxied requests to not crash because they are not local.
        self.check_page(extension, f'http://example.com:{self.server.port}/', 'proxied',
                        True, 'Should be proxied')

        extension.unload()


class ProxyBypassListTest(ProxyBypassBase):

    @classmethod
    def setUpClass(cls):
        with socket.socket() as closed:
            closed.bind(('127.0.0.1', 0))
            port = closed.getsockname()[1]
        cls.prefs = {**ProxyTest.prefs, 'proxy': {
            'mode': 'fixed_servers', 'server': f'127.0.0.1:{port}', 'bypass_list': 'example.com'}}
        super().setUpClass()

    def test_02_webRequest_auth_proxy_no_proxies_on(self):
        extension = self.get_extension()

        # Now check that the pref is respected by addon requests too.
        self.check_page(extension, f'http://example.com:{self.server.port}/', 'not_proxied',
                        False, 'Should have one extra server request')

        extension.unload()
