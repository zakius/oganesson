"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_proxy_speculative.js.

The add-on's code is Firefox's, as it is. Firefox's speculative connection
(Services.io.speculativeConnect()) is a page's <link rel="preconnect"> here,
to a host the proxy applies to (Firefox's test server is at localhost, which
this browser never proxies), and the test waits for the add-on's onRequest
log, where Firefox's waits for Gecko's "speculative-connect-request"
notification. This browser preconnects only with "Preload pages" on,
which is off by default, and the bundled uBlock Origin turns it off again by
default: the port turns both on, as the user can."""

from extension_test_utils import JS
from firefox.head_proxy import ProxyTest
from harness import wait_for

URL = 'http://example.net/'


class ProxySpeculativeTest(ProxyTest):
    # NetworkPredictionOptions::kStandard.
    prefs = {**ProxyTest.prefs, 'net': {'network_prediction_options': 0}}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ubo = cls.browser.ubo_background()
        try:
            ubo.eval('µBlock.changeUserSettings("prefetchingDisabled", false), 0', gesture=False)
        finally:
            ubo.close()

    def test_01_speculative_connect(self):
        handling_ext = self.load_extension(
            manifest={'permissions': ['proxy', '<all_urls>']},
            background=JS(r'''function background() {
    // Handle the proxy request.
    browser.proxy.onRequest.addListener(
      details => {
        browser.test.log(`onRequest ${JSON.stringify(details)}`);
        browser.test.assertEq(
          details.type,
          "speculative",
          "Should have seen a speculative proxy request."
        );
        return [{ type: "direct" }];
      },
      { urls: ["<all_urls>"], types: ["speculative"] }
    );
  }'''))
        handling_ext.startup()

        def asked():
            with open(self.browser.log_path, errors='replace') as log:
                return (f'"token":"{handling_ext.token}","kind":"test-log","args":[true,"onRequest '
                        in log.read())

        page = self.open_tab('about:blank')
        try:
            page.eval(f'''document.head.append(Object.assign(document.createElement("link"),
                {{rel: "preconnect", href: "{URL}"}})), 0''', gesture=False)
            wait_for(asked, timeout=15, what='the speculative connection to ask the add-on')
        finally:
            self.browser.close_target(page)

        handling_ext.unload()
