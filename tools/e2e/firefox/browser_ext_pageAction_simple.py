"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_simple.js.

The add-ons' code is Firefox's, as it is. example.com is a local server here,
with Firefox's file_dummy.html. The page action's button in the location bar,
which these tests check and click, is zakius/oganesson#68
(head.page_action_button(), head.click_page_action()): until it exists, those
checks fail. Firefox's PageActions' `pinnedToUrlbar` is that button: a page
action shows in the location bar.

test_01_pageAction_basic: Firefox's console warning for the unrecognized
property is one of the add-on's install warnings, which the port reads after
the add-on starts, where Firefox reads the console it has watched since then.
Left out: ExtensionTestUtils.failOnSchemaWarnings(), which keeps Firefox's
test harness from failing on that warning, a Gecko internal.

test_03_pageAction_icon_on_subframe_navigation: the page that Firefox's
navigateTab() loads in the selected tab, a data: URL, is a new tab's here,
which the browser loads. SpecialPowers.spawn() is DevTools' evaluation in the
page. TestUtils.waitForCondition() waits 5 seconds, as Firefox's does.
"""

import json
import re

from firefox import head
from extension_test_utils import JS, FirefoxTest
from harness import wait_for

HTML = {'Content-Type': 'text/html'}
DIR = '/browser/browser/components/extensions/test/browser/'
BASE = f'http://example.com{DIR}'
FILE_DUMMY = b'''<html>
<head>
<title>Dummy test page</title>
<meta http-equiv="Content-Type" content="text/html;charset=utf-8"></meta>
</head>
<body>
<p>Dummy test page</p>
<a id="link_to_example_com" href="https://example.com/#linkclick">link</a>
</body>
</html>
'''

# Each add-on's background: Firefox's, as it is.
SHOW_PAGE_ACTION = JS('''function () {
      browser.tabs.query({ active: true, currentWindow: true }, tabs => {
        let tabId = tabs[0].id;

        browser.pageAction.show(tabId).then(() => {
          browser.test.sendMessage("page-action-shown");
        });
      });
    }''')


class PageActionSimpleTest(FirefoxTest):
    hosts = ('example.com',)
    routes = {
        # Firefox's server lists the folder.
        DIR: (200, HTML, b'<!DOCTYPE html><title>browser</title><p>file_dummy.html'),
        f'{DIR}/file_dummy.html': (200, HTML, FILE_DUMMY),
    }

    def test_01_pageAction_basic(self):
        extension = self.load_extension(
            manifest={
                'page_action': {
                    'default_popup': 'popup.html',
                    'unrecognized_property': 'with-a-random-value',
                },
            },

            files={
                'popup.html': '''
      <!DOCTYPE html>
      <html><body>
      <script src="popup.js"></script>
      </body></html>
      ''',

                'popup.js': JS('''function () {
        browser.runtime.sendMessage("from-popup");
      }'''),
            },

            background=JS('''function () {
      browser.runtime.onMessage.addListener(msg => {
        browser.test.assertEq(msg, "from-popup", "correct message received");
        browser.test.sendMessage("popup");
      });
      browser.tabs.query({ active: true, currentWindow: true }, tabs => {
        let tabId = tabs[0].id;

        browser.pageAction.show(tabId).then(() => {
          browser.test.sendMessage("page-action-shown");
        });
      });
    }'''))

        extension.startup()
        warnings = self.browser.extension_info(extension.id)['installWarnings']
        self.check(any(re.search(r'Reading manifest: Warning processing page_action.unrecognized_property: '
                                 'An unexpected property was found', w) for w in warnings),
                   f'the unrecognized property is warned about - Actual: {warnings}')
        extension.await_message('page-action-shown')

        elem = head.page_action_button(self, extension)
        self.check(elem is not None, 'pageAction pinned to urlbar')

        head.click_page_action(self, extension)

        extension.await_message('popup')

        extension.unload()

    def test_02_pageAction_pinned(self):
        extension = self.load_extension(
            manifest={
                'page_action': {
                    'default_popup': 'popup.html',
                    'pinned': False,
                },
            },

            files={
                'popup.html': '''
      <!DOCTYPE html>
      <html><body>
      </body></html>
      ''',
            },

            background=SHOW_PAGE_ACTION)

        extension.startup()
        extension.await_message('page-action-shown')

        # There are plenty of tests for the main action button, we just verify
        # that we've properly set the pinned value.
        self.check(head.page_action_button(self, extension) is not None, 'Check pageAction pinning')

        extension.unload()

    def test_03_pageAction_icon_on_subframe_navigation(self):
        extension = self.load_extension(
            manifest={
                'page_action': {
                    'default_popup': 'popup.html',
                },
            },

            files={
                'popup.html': '''
      <!DOCTYPE html>
      <html><body>
      </body></html>
      ''',
            },

            background=SHOW_PAGE_ACTION)

        tab = self.open_tab('about:blank')
        self.load_url(tab, 'data:text/html,<h1>Top Level Frame</h1>')

        extension.startup()
        extension.await_message('page-action-shown')

        wait_for(lambda: head.page_action_button(self, extension),
                 timeout=5, what='pageAction is initially visible')

        # Create a sub-frame
        subframe_url = f'{BASE}#subframe-url-1'
        tab.eval(f'''(async url => {{
      const iframe = document.createElement("iframe");
      iframe.setAttribute("id", "test-subframe");
      iframe.setAttribute("src", url);
      iframe.setAttribute("style", "height: 200px; width: 200px");

      // Await the initial url to be loaded in the subframe.
      await new Promise(resolve => {{
        iframe.onload = resolve;
        document.body.appendChild(iframe);
      }});
    }})({json.dumps(subframe_url)})''')

        wait_for(lambda: head.page_action_button(self, extension),
                 timeout=5, what='pageAction should be visible when a subframe is created')

        # Navigating the sub-frame
        subframe_url = f'{BASE}/file_dummy.html#subframe-url-2'
        tab.eval(f'''(async url => {{
      const iframe = document.querySelector(
        "iframe#test-subframe"
      );

      // Await the subframe navigation.
      await new Promise(resolve => {{
        iframe.onload = resolve;
        iframe.setAttribute("src", url);
      }});
    }})({json.dumps(subframe_url)})''')

        # Subframe location changed
        wait_for(lambda: head.page_action_button(self, extension),
                 timeout=5, what='pageAction should be visible after a subframe navigation')

        self.browser.close_target(tab)
        extension.unload()
