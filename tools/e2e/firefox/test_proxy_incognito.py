"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_proxy_incognito.js.

The add-ons' code is Firefox's, as it is. Firefox's private content page is a
tab of a private window here. Firefox's server speaks plain HTTP at an
https: URL, as this one does: the page doesn't load, but its request asks
the add-ons for its proxy first."""

from extension_test_utils import JS
from firefox import head
from firefox.head_proxy import ProxyTest

HTML = {'Content-Type': 'text/html'}


class ProxyIncognitoTest(ProxyTest):
    hosts = ('example.com',)
    routes = {'/dummy': (200, HTML, b'<!DOCTYPE html><html></html>')}

    def test_01_incognito_proxy_onRequest_access(self):
        # This extension will fail if it gets a private request.
        extension = self.load_extension(
            manifest={'permissions': ['proxy', '<all_urls>']},
            background=JS(r'''async function background() {
      browser.proxy.onRequest.addListener(
        async details => {
          browser.test.assertFalse(
            details.incognito,
            "incognito flag is not set"
          );
          browser.test.notifyPass("proxy.onRequest");
        },
        { urls: ["<all_urls>"], types: ["main_frame"] }
      );

      // Actual call arguments do not matter here.
      await browser.test.assertRejects(
        browser.proxy.settings.set({
          value: {
            proxyType: "none",
          },
        }),
        /proxy.settings requires private browsing permission/,
        "proxy.settings requires private browsing permission."
      );

      browser.test.sendMessage("ready");
    }'''))
        extension.startup()
        extension.await_message('ready')

        pextension = self.load_extension(
            incognito_override='spanning',
            manifest={'permissions': ['proxy', '<all_urls>']},
            background=JS(r'''function() {
      browser.proxy.onRequest.addListener(
        async details => {
          browser.test.assertTrue(
            details.incognito,
            "incognito flag is set with filter"
          );
          browser.test.sendMessage("proxy.onRequest.private");
        },
        { urls: ["<all_urls>"], types: ["main_frame"], incognito: true }
      );

      browser.proxy.onRequest.addListener(
        async details => {
          browser.test.assertFalse(
            details.incognito,
            "incognito flag is not set with filter"
          );
          browser.test.notifyPass("proxy.onRequest.spanning");
        },
        { urls: ["<all_urls>"], types: ["main_frame"], incognito: false }
      );
    }'''))
        pextension.startup()

        private_tab = head.open_private_window(self)
        private_tab.call('Page.navigate', url='https://example.com/dummy')
        pextension.await_message('proxy.onRequest.private')
        head.close_window(self, head.window_of(self, private_tab))

        content_page = self.browser.new_tab('https://example.com/dummy')
        extension.await_finish('proxy.onRequest')
        pextension.await_finish('proxy.onRequest.spanning')
        self.browser.close_target(content_page)

        pextension.unload()
        extension.unload()
