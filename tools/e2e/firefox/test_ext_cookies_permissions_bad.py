"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_cookies_permissions_bad.html.

Firefox's testCookies() is head_cookies.py's, with its add-on as Firefox has
it. Firefox's init task sets network.cookie.quotaPerHost and maxPerHost to 3,
so that a cookie is evicted; Chromium's limit has no setting (see
head_cookies.py), so the test's count of a host's cookies at the end finds
the cookie that Firefox evicts."""

from extension_test_utils import FirefoxTest
from firefox.head_cookies import test_cookies


class CookiesPermissionsBadTest(FirefoxTest):

    def test_01_bad_cookie_permissions(self):
        # Test non-matching, non-secure domain with non-secure cookie
        test_cookies(self, {
            'permissions': ['http://example.com/', 'cookies'],
            'url': 'http://example.net/',
            'domain': 'example.net',
            'secure': False,
            'shouldPass': False,
            'shouldWrite': False,
        })

        # Test non-matching, secure domain with non-secure cookie
        test_cookies(self, {
            'permissions': ['https://example.com/', 'cookies'],
            'url': 'https://example.net/',
            'domain': 'example.net',
            'secure': False,
            'shouldPass': False,
            'shouldWrite': False,
        })

        # Test non-matching, secure domain with secure cookie
        test_cookies(self, {
            'permissions': ['https://example.com/', 'cookies'],
            'url': 'https://example.net/',
            'domain': 'example.net',
            'secure': False,
            'shouldPass': False,
            'shouldWrite': False,
        })

        # Test matching subdomain with superdomain privileges, secure cookie (http)
        test_cookies(self, {
            'permissions': ['http://foo.bar.example.com/', 'cookies'],
            'url': 'http://foo.bar.example.com/',
            'domain': '.example.com',
            'secure': True,
            'shouldPass': False,
            'shouldWrite': True,
        })

        # Test matching, non-secure domain with secure cookie
        test_cookies(self, {
            'permissions': ['http://example.com/', 'cookies'],
            'url': 'http://example.com/',
            'domain': 'example.com',
            'secure': True,
            'shouldPass': False,
            'shouldWrite': True,
        })

        # Test matching, non-secure host, secure URL
        test_cookies(self, {
            'permissions': ['http://example.com/', 'cookies'],
            'url': 'https://example.com/',
            'domain': 'example.com',
            'secure': True,
            'shouldPass': False,
            'shouldWrite': False,
        })

        # Test non-matching domain
        test_cookies(self, {
            'permissions': ['http://example.com/', 'cookies'],
            'url': 'http://example.com/',
            'domain': 'example.net',
            'secure': False,
            'shouldPass': False,
            'shouldWrite': False,
        })

        # Test invalid scheme
        test_cookies(self, {
            'permissions': ['ftp://example.com/', 'cookies'],
            'url': 'ftp://example.com/',
            'domain': 'example.com',
            'secure': False,
            'shouldPass': False,
            'shouldWrite': False,
        })
