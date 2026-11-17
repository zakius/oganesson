"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_proxy_listener.js.

The add-ons' code is Firefox's, as it is. Gecko's proxy service, which the
test asks for the proxies of a URL (getProxyInfo()), is the browser's NetLog
here (head_proxy.py): Chromium's proxies have no credentials, its SOCKS 5
proxy always resolves the host, and a proxy that fails stays out of use for
5 minutes, where Firefox has the proxy's failoverTimeout. This browser has
no FTP, so it resolves no proxy for an ftp: URL: test_ftp_disabled gets
null, as in Firefox, without a request. test_ws's proxy is head_proxy's
ProxyServer, which refuses each CONNECT, as Firefox's test's server does,
and counts those for the WebSocket's host: the browser's own requests may
go through it too."""

import json

from extension_test_utils import JS
from firefox.head_proxy import (TRANSPARENT_PROXY_RESOLVES_HOST, ProxyServer, ProxyTest,
                                check_proxy_chain)

TEST_DATA = [
    {
        # An ExtensionError is thrown for this, but we are unable to catch it as we
        # do with the PAC script api.  In this case, we expect null for proxyInfo.
        'proxyInfo': 'not_defined',
        'expected': {
            'proxyInfo': None,
        },
    },
    {
        'proxyInfo': 1,
        'expected': {
            'error': {
                'message':
                    'ProxyInfoData: proxyData must be an object or array of objects',
            },
        },
    },
    {
        'proxyInfo': [
            {
                'type': 'socks',
                'host': 'foo.bar',
                'port': 1080,
                'username': 'johnsmith',
                'password': 'pass123',
                'proxyDNS': True,
                'failoverTimeout': 3,
            },
            {'type': 'http', 'host': '192.168.1.1', 'port': 3128},
            {'type': 'https', 'host': '192.168.1.2', 'port': 1121, 'failoverTimeout': 1},
            {
                'type': 'socks',
                'host': '192.168.1.3',
                'port': 1999,
                'proxyDNS': True,
                'username': 'mungosantamaria',
                'password': 'foobar',
            },
            {'type': 'direct'},
        ],
        'expected': {
            'proxyInfo': {
                'type': 'socks',
                'host': 'foo.bar',
                'port': 1080,
                'proxyDNS': True,
                'username': 'johnsmith',
                'password': 'pass123',
                'failoverTimeout': 3,
                'failoverProxy': {
                    'host': '192.168.1.1',
                    'port': 3128,
                    'type': 'http',
                    'failoverProxy': {
                        'host': '192.168.1.2',
                        'port': 1121,
                        'type': 'https',
                        'failoverTimeout': 1,
                        'failoverProxy': {
                            'host': '192.168.1.3',
                            'port': 1999,
                            'type': 'socks',
                            'proxyDNS': TRANSPARENT_PROXY_RESOLVES_HOST,
                            'username': 'mungosantamaria',
                            'password': 'foobar',
                            'failoverProxy': {
                                'type': 'direct',
                            },
                        },
                    },
                },
            },
        },
    },
]

BACKGROUND = JS(r'''function background(proxyInfo) {
    browser.test.log(
      `testing proxy.onRequest with proxyInfo = ${JSON.stringify(proxyInfo)}`
    );
    browser.proxy.onRequest.addListener(
      () => {
        return proxyInfo;
      },
      { urls: ["<all_urls>"] }
    );
  }''')


class ProxyListenerTest(ProxyTest):

    def get_extension(self, expected_proxy_info):
        extension = self.load_extension(
            manifest={'permissions': ['proxy', '<all_urls>']},
            background=JS(BACKGROUND.source, json.dumps(expected_proxy_info)))
        extension.startup()
        return extension

    def test_01_proxy_listener(self):
        extension = self.load_extension(
            manifest={'permissions': ['proxy', '<all_urls>']},
            background=JS(r'''function() {
      // Some tests generate multiple errors, we'll just rely on the first.
      let seenError = false;
      let proxyInfo;
      browser.proxy.onError.addListener(error => {
        if (!seenError) {
          browser.test.sendMessage("proxy-error-received", error);
          seenError = true;
        }
      });

      browser.proxy.onRequest.addListener(
        details => {
          browser.test.log(`onRequest ${JSON.stringify(details)}`);
          if (proxyInfo == "not_defined") {
            return not_defined; // eslint-disable-line no-undef
          }
          return proxyInfo;
        },
        { urls: ["<all_urls>"] }
      );

      browser.test.onMessage.addListener((message, data) => {
        if (message === "set-proxy") {
          seenError = false;
          proxyInfo = data.proxyInfo;
        }
      });

      browser.test.sendMessage("ready");
    }'''))
        extension.startup()
        extension.await_message('ready')

        for test in TEST_DATA:
            extension.send_message('set-proxy', test)
            test_error = test['expected'].get('error')

            proxy_info = self.proxy_info()
            expected_proxy_info = test['expected']['proxyInfo'] if 'proxyInfo' in test['expected'] else None

            if test_error:
                # waiting for error data
                error = extension.await_message('proxy-error-received')
                self.equal((error or {}).get('message'), test_error['message'],
                           'Correct error message received')
                self.equal(proxy_info, None, 'no proxyInfo received')
            elif expected_proxy_info is None:
                self.equal(proxy_info, None, 'no proxyInfo received')
            else:
                left = check_proxy_chain(self, proxy_info, expected_proxy_info, -1)
                self.ok(not left, 'no left over failoverProxy')

        extension.unload()

    def test_02_passthrough(self):
        ext1 = self.get_extension(None)
        ext2 = self.get_extension({'host': '1.2.3.4', 'port': 8888, 'type': 'https'})

        # Also use a restricted url to test the ability to proxy those.
        proxy_info = self.proxy_info('https://addons.mozilla.org/') or {}

        self.equal(proxy_info.get('host'), '1.2.3.4', 'second extension won')
        self.equal(proxy_info.get('port'), '8888', 'second extension won')
        self.equal(proxy_info.get('type'), 'https', 'second extension won')

        ext2.unload()

        proxy_info = self.proxy_info()
        self.equal(proxy_info, None, 'expected no proxy')
        ext1.unload()

    def test_03_ftp_disabled(self):
        extension = self.get_extension({'host': '1.2.3.4', 'port': 8888, 'type': 'http'})

        proxy_info = self.proxy_info('ftp://somewhere.mozilla.org/')

        self.equal(proxy_info, None, 'proxy of ftp request is not available when ftp is disabled')

        extension.unload()

    def test_04_ws(self):
        proxy = ProxyServer()
        try:
            extension = self.get_extension({'host': '127.0.0.1', 'port': proxy.port, 'type': 'http'})

            # We need a page to use the WebSocket constructor, so let's use an extension.
            dummy = self.load_extension(background=JS(r'''function() {
      // The connection will not be upgraded to WebSocket, so it will close.
      let ws = new WebSocket("wss://example.net/");
      ws.onclose = () => browser.test.sendMessage("websocket_closed");
    }'''))
            dummy.startup()
            dummy.await_message('websocket_closed')
            dummy.unload()

            proxy_request_count = proxy.requests.count(('connect', 'example.net:443'))
            self.equal(proxy_request_count, 1, 'Expected one proxy request')
            extension.unload()
        finally:
            proxy.stop()
