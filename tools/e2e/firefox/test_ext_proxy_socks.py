"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_proxy_socks.js.

The add-on's code is Firefox's, as it is. Its SOCKS server is head_proxy's
ProxyServer, which asks for the username and password as Firefox's does.
Firefox proxies its page at localhost with
network.proxy.allow_hijacking_localhost; this browser never proxies a
loopback host, so the page is at example.com, which the SOCKS server answers
itself, as Firefox's does. Left out, as Gecko internals: test_socks_server
and test_tcpsocket_proxy, which check the server with Gecko's socket
transport and proxy filters, and test_onRequest_tcpsocket_proxy, which
proxies Firefox's privileged TCPSocket."""

from extension_test_utils import JS
from firefox.head_proxy import ProxyServer, ProxyTest


class ProxySocksTest(ProxyTest):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.socks_server = ProxyServer(username='foo', password='bar')

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.socks_server.stop()

    def test_01_webRequest_socks_proxy(self):
        handling_ext = self.load_extension(
            manifest={'permissions': ['proxy', 'webRequest', 'webRequestBlocking', '<all_urls>']},
            background=JS(r'''async function background(port) {
    function checkProxyData(details) {
      browser.test.assertEq("127.0.0.1", details.proxyInfo.host, "proxy host");
      browser.test.assertEq(port, details.proxyInfo.port, "proxy port");
      browser.test.assertEq("socks", details.proxyInfo.type, "proxy type");
      browser.test.assertEq(
        "foo",
        details.proxyInfo.username,
        "proxy username not set"
      );
      browser.test.assertEq(
        undefined,
        details.proxyInfo.password,
        "no proxy password passed to webrequest"
      );
    }
    browser.webRequest.onBeforeRequest.addListener(
      details => {
        checkProxyData(details);
      },
      { urls: ["<all_urls>"] }
    );
    browser.webRequest.onAuthRequired.addListener(
      () => {
        // We should never get onAuthRequired for socks proxy
        browser.test.fail("onAuthRequired");
      },
      { urls: ["<all_urls>"] },
      ["blocking"]
    );
    browser.webRequest.onCompleted.addListener(
      details => {
        checkProxyData(details);
        browser.test.sendMessage("done");
      },
      { urls: ["<all_urls>"] }
    );
    browser.proxy.onRequest.addListener(
      () => {
        return [
          {
            type: "socks",
            host: "127.0.0.1",
            port,
            username: "foo",
            password: "bar",
          },
        ];
      },
      { urls: ["<all_urls>"] }
    );
  }''', str(self.socks_server.port)))
        handling_ext.startup()

        content_page = self.browser.new_tab('http://example.com/')

        handling_ext.await_message('done')
        self.browser.close_target(content_page)
        handling_ext.unload()
