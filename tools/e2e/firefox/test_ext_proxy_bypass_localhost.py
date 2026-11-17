"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_proxy_bypass_localhost.js.

The add-on's code is Firefox's, as it is. Its proxy is head_proxy's
ProxyServer, and Firefox's DNS override of example.com is a host rule. The
pages declare no favicon, so that a tab requests nothing more, as Firefox's
content page doesn't. Left out: the checks with
network.proxy.allow_hijacking_localhost on, a Gecko pref that lets add-ons
proxy localhost, which this browser never does (its default is Firefox's),
and with network.proxy.no_proxies_on, the exceptions of Firefox's own proxy
settings, which this browser takes from the system's proxy settings."""

from extension_test_utils import JS
from firefox.head_proxy import ProxyServer, ProxyTest

# A page that asks for no favicon.
PAGE = (200, {'Content-Type': 'text/html'}, b'<!DOCTYPE html><link rel="icon" href="data:,">')


class ProxyBypassLocalhostTest(ProxyTest):
    hosts = ('example.com',)
    routes = {'/': PAGE}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.proxy = ProxyServer(answer=PAGE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.proxy.stop()

    def server_count(self):
        return self.server.requests.count('/')

    def proxy_count(self):
        return sum(1 for request in self.proxy.requests if request[0] == 'http')

    def load_content_page(self, url):
        """ExtensionTestUtils.loadContentPage(), closed by the caller."""
        return self.browser.new_tab(url)

    def test_01_webRequest_auth_proxy(self):
        port = self.proxy.port
        extension = self.load_extension(
            manifest={
                'permissions': ['proxy', 'webRequest', 'webRequestBlocking', '<all_urls>'],
                'host_permissions': [
                    f'http://localhost:{self.server.port}/*',
                    'http://localhost/*',
                ],
            },
            background=JS(r'''function background(port) {
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
  }''', str(port)))
        extension.startup()

        # The request doesn't allow the webextension to force the proxying of
        # a localhost request.
        proxy_count = self.proxy_count()
        server_count = self.server_count()
        content_page = self.load_content_page(f'http://localhost:{self.server.port}/')
        self.equal(extension.await_message('requestCompleted'), 'not_proxied', 'requestCompleted')
        self.equal(self.proxy_count(), proxy_count, "Shouldn't see any proxy requests")
        self.equal(self.server_count(), server_count + 1, 'Should have one extra server request')
        self.browser.close_target(content_page)

        # Make sure unproxied requests to not crash because they are not local.
        proxy_count = self.proxy_count()
        server_count = self.server_count()
        content_page = self.load_content_page(f'http://example.com:{self.server.port}/')
        self.equal(extension.await_message('requestCompleted'), 'proxied', 'requestCompleted')
        self.equal(self.proxy_count(), proxy_count + 1, 'Should be proxied')
        self.equal(self.server_count(), server_count, 'No extra direct requests')
        self.browser.close_target(content_page)

        extension.unload()
