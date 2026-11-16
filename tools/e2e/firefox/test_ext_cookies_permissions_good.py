"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_cookies_permissions_good.html.

Firefox's testCookies() is head_cookies.py's, with its add-on as Firefox has
it. Firefox's init task sets network.cookie.quotaPerHost and maxPerHost to 3,
so that a cookie is evicted; Chromium's limit has no setting (see
head_cookies.py), so the eviction checks fail here."""

from extension_test_utils import FirefoxTest
from firefox.head_cookies import test_cookies


class CookiesPermissionsGoodTest(FirefoxTest):

    def test_01_good_cookie_permissions(self):
        # Test matching, non-secure domain with non-secure cookie
        test_cookies(self, {
            'permissions': ['http://example.com/', 'cookies'],
            'url': 'http://example.com/',
            'domain': 'example.com',
            'secure': False,
            'shouldPass': True,
        })

        # Test matching, secure domain with non-secure cookie
        test_cookies(self, {
            'permissions': ['https://example.com/', 'cookies'],
            'url': 'https://example.com/',
            'domain': 'example.com',
            'secure': False,
            'shouldPass': True,
        })

        # Test matching, secure domain with secure cookie
        test_cookies(self, {
            'permissions': ['https://example.com/', 'cookies'],
            'url': 'https://example.com/',
            'domain': 'example.com',
            'secure': True,
            'shouldPass': True,
        })

        # Test matching subdomain with superdomain privileges, secure cookie (https)
        test_cookies(self, {
            'permissions': ['https://foo.bar.example.com/', 'cookies'],
            'url': 'https://foo.bar.example.com/',
            'domain': '.example.com',
            'secure': True,
            'shouldPass': True,
        })

        # Test matching subdomain with superdomain privileges, non-secure cookie (https)
        test_cookies(self, {
            'permissions': ['https://foo.bar.example.com/', 'cookies'],
            'url': 'https://foo.bar.example.com/',
            'domain': '.example.com',
            'secure': False,
            'shouldPass': True,
        })

        # Test matching subdomain with superdomain privileges, non-secure cookie  (http)
        test_cookies(self, {
            'permissions': ['http://foo.bar.example.com/', 'cookies'],
            'url': 'http://foo.bar.example.com/',
            'domain': '.example.com',
            'secure': False,
            'shouldPass': True,
        })
