"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_pageAction_onClicked.html.

The add-on's code is Firefox's, as it is. The mochitest runs in a page of
mochi.test, which is the active tab here too, from a local server.
AppTestDelegate.clickPageAction() clicks the page action's button in the
location bar, which is zakius/oganesson#68 (head.click_page_action()).
closePageAction() closes the page action's popup, and this add-on has none:
it does nothing. Left out of test_02_pageAction_onClicked_persistent_event:
assertPersistentListeners(), which reads Gecko's primed listeners.
`terminateBackground()` is quick with EVENT_PAGE_ARGS.
"""

from firefox import head
from extension_test_utils import EVENT_PAGE_ARGS, JS, FirefoxTest

HTML = {'Content-Type': 'text/html'}
PAGE = '/tests/toolkit/components/extensions/test/mochitest/test_ext_pageAction_onClicked.html'


class PageActionOnClickedTest(FirefoxTest):
    browser_args = (*FirefoxTest.browser_args, *EVENT_PAGE_ARGS)
    hosts = ('mochi.test',)
    routes = {PAGE: (200, HTML, b'<!DOCTYPE html><title>pageAction.onClicked test</title>')}

    def setUp(self):
        super().setUp()
        page = self.open_tab(f'http://mochi.test:8888{PAGE}')
        self.addCleanup(self.browser.close_target, page)

    def create_extension(self, background=None):
        return self.load_extension(
            manifest={
                'background': background or {},
                'page_action': {'show_matches': ['<all_urls>']},
            },
            background=JS('''async function () {
      async function checkIsHandlingUserInput() {
        try {
          // permissions.request is declared with requireUserInput,
          // so it would reject if inputHandling is false.
          let granted = await browser.permissions.request({});
          // We haven't requested any permissions, so the API call grants the
          // requested permissions without actually prompting the user.
          browser.test.assertTrue(granted, "empty permissions granted");
          return true;
        } catch (e) {
          browser.test.assertEq(
            e?.message,
            "permissions.request may only be called from a user input handler",
            "Expected error when permissions.request rejects"
          );
          return false;
        }
      }
      browser.pageAction.onClicked.addListener(async () => {
        browser.test.assertTrue(
          await checkIsHandlingUserInput(),
          "pageAction.onClicked is handling user input"
        );
        browser.test.notifyPass("action-clicked");
      });

      // Sanity check: Verify that pageAction is shown (because it needs to be
      // in order to trigger pageAction.onClicked).
      let [tab] = await browser.tabs.query({
        active: true,
        currentWindow: true,
      });
      browser.test.assertTrue(
        await browser.pageAction.isShown({ tabId: tab.id }),
        "pageAction should be visible (due to page_action.show_matches)"
      );

      browser.test.assertFalse(
        await checkIsHandlingUserInput(),
        "not handling user input by default"
      );
      browser.test.sendMessage("background-ready");
    }'''))

    def test_01_pageAction_onClicked_and_inputHandling(self):
        extension = self.create_extension()

        extension.startup()
        extension.await_message('background-ready')

        head.click_page_action(self, extension)
        extension.await_finish('action-clicked')

        extension.unload()

    def test_02_pageAction_onClicked_persistent_event(self):
        extension = self.create_extension({'persistent': False})

        extension.startup()
        extension.await_message('background-ready')

        extension.terminate_background()

        head.click_page_action(self, extension)

        # Background script will run again.
        extension.await_message('background-ready')
        extension.await_finish('action-clicked')

        extension.unload()
