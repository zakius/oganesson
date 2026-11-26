"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_dnr_loadingPrincipal.js.

The add-on's code is Firefox's, as it is. ExtensionTestUtils.loadContentPage()
is a new tab, and the content task's getComputedStyle() runs in it. Left out
as a Gecko internal: ChromeUtils.clearResourceCache(), which Firefox's test
calls "likely not needed"; each tab loads the stylesheets again."""

from extension_test_utils import JS, FirefoxTest


def css(text):
    return (200, {'Content-Type': 'text/css'}, text)


class DnrLoadingPrincipalTest(FirefoxTest):
    hosts = ('page.example', 'style.example', 'import.example')
    routes = {
        '/page.html': (200, {'Content-Type': 'text/html'},
                       b'<link rel="stylesheet" href="http://style.example/parent.css">'),
        '/parent.css': css(b"""
    @import url('http://import.example/child.css');
    :root { --style-status: dnr_blocked_style; }
  """),
        '/child.css': css(b'body { --style-status: dnr_not_matched }'),
    }

    def check_is_stylesheet_blocked(self, url):
        content_page = self.open_tab(url)
        result = content_page.eval(
            'getComputedStyle(document.body).getPropertyValue("--style-status")').strip()
        self.browser.close_target(content_page)
        if result not in ('dnr_blocked_style', 'dnr_not_matched'):
            raise AssertionError(f'Unexpected --style-status: {result}')
        return result

    def start_dnr_extension(self, host_permissions):
        extension = self.load_extension(
            manifest={
                'manifest_version': 3,
                # Note: using the DNR permission that requires host permissions.
                'permissions': ['declarativeNetRequestWithHostAccess'],
                'host_permissions': host_permissions,
                'granted_host_permissions': True,
            },
            background=JS(r'''async function() {
      await browser.declarativeNetRequest.updateSessionRules({
        addRules: [
          {
            id: 1,
            condition: { urlFilter: "child.css" },
            action: { type: "block" },
          },
        ],
      });
      browser.test.sendMessage("dnr_registered");
    }'''))
        extension.startup()
        extension.await_message('dnr_registered')
        return extension

    def test_01_css_import_blocked_with_document_host_permission(self):
        extension = self.start_dnr_extension([
            '*://page.example/*',  # loading principal.
            # '*://style.example/*',  # triggering principal.
            '*://import.example/*',  # requested URL.
        ])

        # With permissions for the loading principal and requested URL, DNR applies.
        self.is_(self.check_is_stylesheet_blocked('http://page.example/page.html'),
                 'dnr_blocked_style',
                 'Blocked by DNR: the extension has host permissions for the document')

        extension.unload()

    def test_02_css_import_allowed_without_document_host_permission(self):
        extension = self.start_dnr_extension([
            # '*://page.example/*',  # loading principal.
            '*://style.example/*',  # triggering principal.
            '*://import.example/*',  # requested URL.
        ])

        # Lack of permission for loading principal results in DNR not applying.
        self.is_(self.check_is_stylesheet_blocked('http://page.example/page.html'),
                 'dnr_not_matched',
                 'Not blocked by DNR: the extension lacks host permissions for the document')

        extension.unload()
