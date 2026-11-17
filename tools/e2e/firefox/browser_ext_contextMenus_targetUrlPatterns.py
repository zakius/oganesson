"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_targetUrlPatterns.js.

The add-on's page has this browser's scheme, so the case of a link to an
add-on's page has `chrome-extension:` where Firefox has `moz-extension:`.
Left out: privileged_are_allowed_to_use_restrictedSchemes, which checks that
only a privileged add-on (Mozilla's own, with the `mozillaAddons`
permission) gets an item on Firefox's reader view (`about:reader`), a Gecko
internal."""

import json

from firefox import head
from extension_test_utils import JS

TESTCASES = [
    {
        # Link to URL with query string parameters only.
        'testUrl': 'magnet:?xt=urn:btih:somesha1hash&dn=displayname.txt',
        'matchingPatterns': [
            'magnet:*',
            'magnet:?xt=*',
            'magnet:?xt=*txt',
            'magnet:*?xt=*txt',
        ],
        'nonmatchingPatterns': [
            # Although <all_urls> matches unsupported schemes in Chromium,
            # we have specified that <all_urls> only matches all supported
            # schemes. To match any scheme, an extension should not set the
            # targetUrlPatterns field - this is checked below in subtest
            # unsupportedSchemeWithoutTargetUrlPatterns.
            '<all_urls>',
            'agnet:*',
            'magne:*',
        ],
    },
    {
        # Link to bookmarklet.
        'testUrl': 'javascript:-URL',
        'matchingPatterns': ['javascript:*', 'javascript:*URL', 'javascript:-URL'],
        'nonmatchingPatterns': [
            '<all_urls>',
            'javascript://-URL',
            'javascript:javascript:-URL',
        ],
    },
    {
        # Link to bookmarklet with comment.
        'testUrl': 'javascript://-URL',
        'matchingPatterns': [
            'javascript:*',
            'javascript://-URL',
            'javascript:*URL',
        ],
        'nonmatchingPatterns': ['<all_urls>', 'javascript:-URL'],
    },
    {
        # Link to data-URI.
        'testUrl': 'data:application/foo,bar',
        'matchingPatterns': [
            '<all_urls>',
            'data:application/foo,bar',
            'data:*,*',
            'data:*',
        ],
        'nonmatchingPatterns': ['data:,bar', 'data:application/foo,'],
    },
    {
        # Extension page.
        'testUrl': 'chrome-extension://uuid/manifest.json',
        'matchingPatterns': ['chrome-extension://*/*'],
        'nonmatchingPatterns': [
            '<all_urls>',
            'chrome-extension://uuid/not/manifest.json*',
        ],
    },
    {
        # While the scheme is supported, the URL is invalid.
        'testUrl': 'http://',
        'matchingPatterns': [],
        'nonmatchingPatterns': ['http://*/*', '<all_urls>'],
    },
]

TEST_SCRIPT = JS('''async function testScript() {
  let testcase;

  browser.contextMenus.onShown.addListener(({ menuIds, linkUrl }) => {
    browser.test.assertEq(testcase.testUrl, linkUrl, "Expected linkUrl");
    for (let pattern of testcase.matchingPatterns) {
      browser.test.assertTrue(
        menuIds.includes(pattern),
        `Menu item with targetUrlPattern="${pattern}" should be shown at ${testcase.testUrl}`
      );
    }
    for (let pattern of testcase.nonmatchingPatterns) {
      browser.test.assertFalse(
        menuIds.includes(pattern),
        `Menu item with targetUrlPattern="${pattern}" should not be shown at ${testcase.testUrl}`
      );
    }
    testcase = null;
    browser.test.sendMessage("onShown_checked");
  });

  browser.test.onMessage.addListener(async (msg, params) => {
    browser.test.assertEq("setupTest", msg, "Expected message");

    // Save test case in global variable for use in the onShown event.
    testcase = params;
    browser.test.log(`Running test for link with URL: ${testcase.testUrl}`);
    document.getElementById("test_link_element").href = testcase.testUrl;
    await browser.contextMenus.removeAll();
    for (let targetUrlPattern of [
      ...testcase.matchingPatterns,
      ...testcase.nonmatchingPatterns,
    ]) {
      await new Promise(resolve => {
        browser.test.log(`Creating menu with "${targetUrlPattern}"`);
        browser.contextMenus.create(
          {
            id: targetUrlPattern,
            contexts: ["link"],
            title: "Some menu item",
            targetUrlPatterns: [targetUrlPattern],
          },
          resolve
        );
      });
    }
    browser.test.sendMessage("setupTest_ready");
  });
  browser.test.sendMessage("ready");
}''')


class ContextMenusTargetUrlPatternsTest(head.ContextMenuTest):

    def test_01_unsupported_schemes(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function () {
              browser.tabs.create({ url: "testrunner.html" });
            }'''),
            files={
                'testrunner.js': TEST_SCRIPT,
                'testrunner.html': '''
                  <!DOCTYPE html><meta charset="utf-8">
                  <body>
                  <a id="test_link_element">Test link</a>
                  <script src="testrunner.js"></script>
                  </body>
                ''',
            })

        extension.startup()
        extension.await_message('ready')
        page = head.extension_tab(self, extension, 'testrunner.html')
        for testcase in TESTCASES:
            extension.send_message('setupTest', testcase)
            extension.await_message('setupTest_ready')

            head.open_extension_context_menu(self, page, '#test_link_element')
            extension.await_message('onShown_checked')
            head.close_context_menu(self)
        extension.unload()

    def link_menu_without_target_url_patterns(self, link_url):
        """testLinkMenuWithoutTargetUrlPatterns()"""
        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function background(expectedLinkUrl) {
              let menuId;
              browser.contextMenus.onShown.addListener(({ menuIds, linkUrl }) => {
                browser.test.assertEq(1, menuIds.length, "Expected number of menus");
                browser.test.assertEq(menuId, menuIds[0], "Expected menu ID");
                browser.test.assertEq(expectedLinkUrl, linkUrl, "Expected linkUrl");
                browser.test.sendMessage("done");
              });
              menuId = browser.contextMenus.create(
                {
                  contexts: ["link"],
                  title: "Test menu item without targetUrlPattern",
                },
                () => {
                  browser.tabs.create({ url: "testpage.html" });
                }
              );
            }''', json.dumps(link_url)),
            files={
                'testpage.js': 'browser.test.sendMessage("ready")',
                'testpage.html': f'''
                  <!DOCTYPE html><meta charset="utf-8">
                  <a id="test_link_element" href="{link_url}">Test link</a>
                  <script src="testpage.js"></script>
                ''',
            })

        extension.startup()
        extension.await_message('ready')
        page = head.extension_tab(self, extension, 'testpage.html')
        head.open_extension_context_menu(self, page, '#test_link_element')
        extension.await_message('done')
        head.close_context_menu(self)

        extension.unload()

    # Tests that a menu item is shown on links with an unsupported scheme if
    # targetUrlPatterns is not set.
    def test_02_unsupported_scheme_without_pattern(self):
        self.link_menu_without_target_url_patterns('unsupported-scheme:data')

    # Tests that a menu item is shown on links with an invalid http:-URL if
    # targetUrlPatterns is not set.
    def test_03_invalid_http_url_without_pattern(self):
        self.link_menu_without_target_url_patterns('http://')
