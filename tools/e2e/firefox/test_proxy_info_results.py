"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_proxy_info_results.js.

The add-on's code is Firefox's, as it is. Gecko's proxy service, which the
test asks for the proxies of a URL, is the browser's NetLog here
(head_proxy.py): Chromium's proxies have no credentials, its SOCKS 5 proxy
always resolves the host, and a proxy that fails stays out of use for 5
minutes, where Firefox has the proxy's failoverTimeout. This browser has no
FTP, so it resolves no proxy for an ftp: URL: Firefox's test then checks
nothing."""

from extension_test_utils import JS
from firefox.head_proxy import TRANSPARENT_PROXY_RESOLVES_HOST, ProxyTest, check_proxy_chain

TESTS = [
    {
        'proxy': 5,
        'expected': {'error': 'ProxyInfoData: proxyData must be an object or array of objects'},
    },
    {
        'proxy': 'INVALID',
        'expected': {'error': 'ProxyInfoData: proxyData must be an object or array of objects'},
    },
    {
        'proxy': {'type': 'socks'},
        'expected': {'error': 'ProxyInfoData: Invalid proxy server host: "undefined"'},
    },
    {
        'proxy': [
            {
                'type': 'pptp',
                'host': 'foo.bar',
                'port': 1080,
                'username': 'mungosantamaria',
                'password': 'pass123',
                'proxyDNS': True,
                'failoverTimeout': 3,
            },
            {
                'type': 'http',
                'host': '192.168.1.1',
                'port': 1128,
                'username': 'mungosantamaria',
                'password': 'word321',
            },
        ],
        'expected': {'error': 'ProxyInfoData: Invalid proxy server type: "pptp"'},
    },
    {
        'proxy': [
            {
                'type': 'http',
                'host': 'foo.bar',
                'port': 65536,
                'username': 'mungosantamaria',
                'password': 'pass123',
                'proxyDNS': True,
                'failoverTimeout': 3,
            },
            {
                'type': 'http',
                'host': '192.168.1.1',
                'port': 3128,
                'username': 'mungosantamaria',
                'password': 'word321',
            },
        ],
        'expected': {'error': 'ProxyInfoData: Proxy server port 65536 outside range 1 to 65535'},
    },
    {
        'proxy': [
            {'type': 'socks', 'host': 'foo.bar', 'port': 3128, 'proxyAuthorizationHeader': 'test'}
        ],
        'expected': {
            'error': 'ProxyInfoData: ProxyAuthorizationHeader requires type "https" or '
            '"http" or "masque"'
        },
    },
    {
        'proxy': [
            {'type': 'http', 'host': 'foo.bar', 'port': 3128, 'connectionIsolationKey': 1234}
        ],
        'expected': {'error': 'ProxyInfoData: Invalid proxy connection isolation key: "1234"'},
    },
    {'proxy': [{'type': 'direct'}], 'expected': {'proxyInfo': None}},
    {
        'proxy': {'host': '1.2.3.4', 'port': '8080', 'type': 'http', 'failoverProxy': None},
        'expected': {
            'proxyInfo': {'host': '1.2.3.4', 'port': '8080', 'type': 'http', 'failoverProxy': None}
        },
    },
    {
        'uri': 'ftp://mozilla.org',
        'proxy': {'host': '1.2.3.4', 'port': '8180', 'type': 'http', 'failoverProxy': None},
        'expected': {
            'proxyInfo': {'host': '1.2.3.4', 'port': '8180', 'type': 'http', 'failoverProxy': None}
        },
    },
    {
        'proxy': {'host': '2.3.4.5', 'port': '8181', 'type': 'http', 'failoverProxy': None},
        'expected': {
            'proxyInfo': {'host': '2.3.4.5', 'port': '8181', 'type': 'http', 'failoverProxy': None}
        },
    },
    {
        'proxy': {
            'host': '1.2.3.4',
            'port': '8080',
            'type': 'http',
            'failoverProxy': {
                'host': '4.4.4.4',
                'port': '9000',
                'type': 'socks',
                'failoverProxy': {'type': 'direct', 'host': None, 'port': -1},
            },
        },
        'expected': {
            'proxyInfo': {
                'host': '1.2.3.4',
                'port': '8080',
                'type': 'http',
                'failoverProxy': {
                    'host': '4.4.4.4',
                    'port': '9000',
                    'type': 'socks',
                    'failoverProxy': {'type': 'direct', 'host': None, 'port': -1},
                },
            }
        },
    },
    {
        'proxy': [{'type': 'http', 'host': 'foo.bar', 'port': 3128}],
        'expected': {'proxyInfo': {'host': 'foo.bar', 'port': 3128, 'type': 'http'}},
    },
    {
        'proxy': {'host': 'foo.bar', 'port': '1080', 'type': 'socks'},
        'expected': {'proxyInfo': {'host': 'foo.bar', 'port': '1080', 'type': 'socks'}},
    },
    {
        'proxy': {'host': 'foo.bar', 'port': '1080', 'type': 'socks4'},
        'expected': {'proxyInfo': {'host': 'foo.bar', 'port': '1080', 'type': 'socks4'}},
    },
    {
        'proxy': [{'type': 'https', 'host': 'foo.bar', 'port': 3128}],
        'expected': {'proxyInfo': {'host': 'foo.bar', 'port': 3128, 'type': 'https'}},
    },
    {
        'proxy': [
            {
                'type': 'socks',
                'host': 'foo.bar',
                'port': 1080,
                'username': 'mungo',
                'password': 'santamaria123',
                'proxyDNS': True,
                'failoverTimeout': 5,
            }
        ],
        'expected': {
            'proxyInfo': {
                'type': 'socks',
                'host': 'foo.bar',
                'port': 1080,
                'username': 'mungo',
                'password': 'santamaria123',
                'failoverTimeout': 5,
                'failoverProxy': None,
                'proxyDNS': TRANSPARENT_PROXY_RESOLVES_HOST,
            }
        },
    },
    {
        'proxy': [
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
                            'failoverProxy': {'type': 'direct'},
                        },
                    },
                },
            }
        },
    },
    {
        'proxy': [
            {
                'type': 'https',
                'host': 'foo.bar',
                'port': 3128,
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
            }
        ],
        'expected': {
            'proxyInfo': {
                'host': 'foo.bar',
                'port': 3128,
                'type': 'https',
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
            }
        },
    },
    {
        'proxy': [
            {
                'type': 'http',
                'host': 'foo.bar',
                'port': 3128,
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
            }
        ],
        'expected': {
            'proxyInfo': {
                'host': 'foo.bar',
                'port': 3128,
                'type': 'http',
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
            }
        },
    },
    {
        'proxy': [
            {
                'type': 'http',
                'host': 'foo.bar',
                'port': 8080,
                'username': 'mungosantamaria',
                'password': 'pass123',
                'proxyDNS': True,
                'failoverTimeout': 3,
                'masqueTemplate': '/.well-known/masque/udp/{target_host}/{target_port}/',
            }
        ],
        'expected': {
            'error': 'ProxyInfoData: masqueTemplate can only be used for "masque" proxies'
        },
    },
    {
        'proxy': [
            {
                'host': 'foo.bar',
                'port': 3128,
                'masqueTemplate': '/.well-known/masque/udp/{target_host}/{target_port}/',
                'type': 'masque',
            }
        ],
        'expected': {
            'proxyInfo': {
                'host': 'foo.bar',
                'port': 3128,
                'type': 'masque',
                'masqueTemplate': '/.well-known/masque/udp/{target_host}/{target_port}/',
            }
        },
    },
    {
        'proxy': [
            {
                'host': 'foo.bar',
                'port': 3128,
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
                'masqueTemplate': '/.well-known/masque/udp/{target_host}/{target_port}/',
                'type': 'masque',
            }
        ],
        'expected': {
            'proxyInfo': {
                'host': 'foo.bar',
                'port': 3128,
                'type': 'masque',
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
                'masqueTemplate': '/.well-known/masque/udp/{target_host}/{target_port}/',
            }
        },
    },
    {
        'proxy': [
            {
                'type': 'masque',
                'host': 'foo.bar',
                'port': 3128,
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
            }
        ],
        'expected': {'error': 'ProxyInfoData: Invalid proxy masque template: "undefined"'},
    },
    {
        'proxy': [
            {
                'type': 'masque',
                'host': 'foo.bar',
                'port': 3128,
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
                'masqueTemplate': '/.well-known/masque/udp/{target_host}/{target_port}/',
                'username': 'mungosantamaria',
            }
        ],
        'expected': {'error': 'ProxyInfoData: Username not expected for "masque" proxy info'},
    },
    {
        'proxy': [
            {
                'host': 'foo.bar',
                'port': 3128,
                'proxyAuthorizationHeader': 'test',
                'connectionIsolationKey': 'key',
                'masqueTemplate': '/.well-known/masque/udp/{target_host}/{target_port}/',
                'type': 'masque',
                'password': 'pass123',
            }
        ],
        'expected': {'error': 'ProxyInfoData: Password not expected for "masque" proxy info'},
    },
]


class ProxyInfoResultsTest(ProxyTest):
    def setup_proxy_result(self, extension, proxy):
        extension.send_message('set-proxy', {'proxy': proxy})
        proxy_info_sent = extension.await_message('proxy-set')
        self.check(
            proxy_info_sent == proxy,
            f'got back proxy data from the proxy listener - Expected: {proxy}, '
            f'Actual: {proxy_info_sent}',
        )

    def check_proxy_resolution(self, extension, test):
        uri, proxy, expected = test['uri'], test['proxy'], test['expected']
        proxy_info = self.proxy_info(uri)

        expected_proxy_info = expected.get('proxyInfo')
        if expected.get('error'):
            self.equal(proxy_info, None, 'Expected proxyInfo to be null')
            error = extension.await_message('proxy-error-received') or {}
            self.equal(error.get('message'), expected['error'], 'error received')
        elif proxy is None:
            self.equal(proxy_info, expected_proxy_info, 'proxy is direct')
        else:
            check_proxy_chain(self, proxy_info, expected_proxy_info)

    def test_01_proxyInfo_results(self):
        extension = self.load_extension(
            manifest={'permissions': ['proxy', '<all_urls>']},
            background=JS(r"""function() {
      let settings = { proxy: null };

      browser.proxy.onError.addListener(error => {
        browser.test.log(`error received ${error.message}`);
        browser.test.sendMessage("proxy-error-received", error);
      });
      browser.test.onMessage.addListener((message, data) => {
        if (message === "set-proxy") {
          settings.proxy = data.proxy;
          browser.test.sendMessage("proxy-set", settings.proxy);
        }
      });
      browser.proxy.onRequest.addListener(
        () => {
          return settings.proxy;
        },
        { urls: ["<all_urls>"] }
      );
    }"""),
        )
        extension.startup()

        for test in TESTS:
            self.setup_proxy_result(extension, test['proxy'])
            test.setdefault('uri', 'http://www.mozilla.org/')
            self.check_proxy_resolution(extension, test)

        extension.unload()
