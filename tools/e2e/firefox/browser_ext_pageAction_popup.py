"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_popup.js.

The add-ons' code is Firefox's, as it is. example.com is a local server here.
clickPageAction() is a real click on the add-on's page action button in the
location bar (head.click_page_action()), and its `button: 1` a middle click
there. Firefox's popup panel is the popup bubble here, Chromium's
ExtensionPopup, read through UI DevTools (head_pageAction.popup_view()): the
panel exists when the add-on's popup page is open, it is shown when the
bubble shows, and hidePopup() closes the popup page. Firefox's count of the
add-on's views (assertViewCount()) is the count of its pages open in the
browser, its DevTools targets. gBrowser.tabs[0], the tab the test switches
to, is a tab other than the test's.

Left out: PromiseTestUtils.allowMatchingRejectionsGlobally(), which keeps
Firefox's test harness from failing on packaging errors, and forceGC(), Gecko
internals.

test_02_page_action_security: Firefox refuses an add-on whose popup is a
chrome: URL; here the browser's refusal to load it is the rejected startup.
Left out: the console message Firefox's security manager logs for the
refusal ("Access to restricted URI denied"), a Gecko internal.
"""

from firefox import head, head_pageAction
from extension_test_utils import JS, FirefoxTest
from harness import Page

HTML = {'Content-Type': 'text/html'}


def script_page(url):
    return f'<html><head><meta charset="utf-8"><script src="{url}"></script></head></html>'


def assert_view_count(test, extension, count):
    """assertViewCount(): the add-on has `count` pages open."""
    prefix = f'chrome-extension://{extension.id}/'
    views = [t for t in test.browser.targets() if t['url'].startswith(prefix)]
    test.is_(len(views), count, 'Should have the expected number of extension views')


class PageActionPopupTest(FirefoxTest):
    hosts = ('example.com',)
    routes = {'/': (200, HTML, b'<!DOCTYPE html><title>example.com</title>')}

    def test_01_page_action_popup(self):
        # A tab to switch to, as Firefox's window has its first tab.
        other_tabs = [t['id'] for t in self.browser.targets() if t['type'] == 'page'
                      and not t['url'].startswith('chrome-extension://')]
        tab = self.open_tab('http://example.com/')

        extension = self.load_extension(
            manifest={
                'background': {
                    'page': 'data/background.html',
                },
                'page_action': {
                    'default_popup': 'popup-a.html',
                },
            },

            files={
                'popup-a.html': script_page('popup-a.js'),
                'popup-a.js': JS('''function () {
        window.onload = () => {
          let background = window.getComputedStyle(
            document.body
          ).backgroundColor;
          browser.test.assertEq("rgba(0, 0, 0, 0)", background);
          browser.runtime.sendMessage("from-popup-a");
        };
        browser.runtime.onMessage.addListener(msg => {
          if (msg == "close-popup") {
            window.close();
          }
        });
      }'''),

                'data/popup-b.html': script_page('popup-b.js'),
                'data/popup-b.js': JS('''function () {
        browser.runtime.sendMessage("from-popup-b");
      }'''),

                'data/background.html': script_page('background.js'),

                'data/background.js': JS('''async function () {
        let tabId;

        let sendClick;
        let tests = [
          () => {
            sendClick({ expectEvent: false, expectPopup: "a" });
          },
          () => {
            sendClick({ expectEvent: false, expectPopup: "a" });
          },
          () => {
            browser.pageAction.setPopup({ tabId, popup: "popup-b.html" });
            sendClick({ expectEvent: false, expectPopup: "b" });
          },
          () => {
            sendClick({ expectEvent: false, expectPopup: "b" });
          },
          () => {
            sendClick({
              expectEvent: true,
              expectPopup: "b",
              middleClick: true,
            });
          },
          () => {
            browser.pageAction.setPopup({ tabId, popup: "" });
            sendClick({ expectEvent: true, expectPopup: null });
          },
          () => {
            sendClick({ expectEvent: true, expectPopup: null });
          },
          () => {
            browser.pageAction.setPopup({ tabId, popup: "/popup-a.html" });
            sendClick({
              expectEvent: false,
              expectPopup: "a",
              runNextTest: true,
            });
          },
          () => {
            browser.test.sendMessage("next-test", { expectClosed: true });
          },
          () => {
            sendClick({
              expectEvent: false,
              expectPopup: "a",
              runNextTest: true,
            });
          },
          () => {
            browser.test.sendMessage("next-test", { closeOnTabSwitch: true });
          },
        ];

        let expect = {};
        sendClick = ({
          expectEvent,
          expectPopup,
          runNextTest,
          middleClick,
        }) => {
          expect = { event: expectEvent, popup: expectPopup, runNextTest };

          browser.test.sendMessage("send-click", middleClick ? 1 : 0);
        };

        browser.runtime.onMessage.addListener(msg => {
          if (msg == "close-popup") {
            return;
          } else if (expect.popup) {
            browser.test.assertEq(
              msg,
              `from-popup-${expect.popup}`,
              "expected popup opened"
            );
          } else {
            browser.test.fail(`unexpected popup: ${msg}`);
          }

          expect.popup = null;
          if (expect.runNextTest) {
            expect.runNextTest = false;
            tests.shift()();
          } else {
            browser.test.sendMessage("next-test");
          }
        });

        browser.pageAction.onClicked.addListener((tab, info) => {
          if (expect.event) {
            browser.test.succeed("expected click event received");
          } else {
            browser.test.fail("unexpected click event");
          }
          expect.event = false;

          if (info.button == 1) {
            browser.pageAction.openPopup();
            return;
          }

          browser.test.sendMessage("next-test");
        });

        browser.test.onMessage.addListener(msg => {
          if (msg == "close-popup") {
            browser.runtime.sendMessage("close-popup");
            return;
          }

          if (msg != "next-test") {
            browser.test.fail("Expecting 'next-test' message");
          }

          if (expect.event) {
            browser.test.fail(
              "Expecting click event before next test but none occurred"
            );
          }

          if (expect.popup) {
            browser.test.fail(
              "Expecting popup before next test but none were shown"
            );
          }

          if (tests.length) {
            let test = tests.shift();
            test();
          } else {
            browser.test.notifyPass("pageaction-tests-done");
          }
        });

        let [tab] = await browser.tabs.query({
          active: true,
          currentWindow: true,
        });
        tabId = tab.id;

        await browser.pageAction.show(tabId);
        browser.test.sendMessage("next-test");
      }'''),
            })

        # Both of the add-on's messages, in the order it sends them.
        steps = []
        extension.on_message('send-click', lambda button: steps.append(('send-click', button)))
        extension.on_message('next-test',
                             lambda expecting=None: steps.append(('next-test', expecting or {})))

        extension.startup()
        while True:
            self.wait_reports(lambda: steps or extension.done, "the add-on's next step")
            if not steps:
                break
            kind, value = steps.pop(0)
            if kind == 'send-click':
                if value == 1:
                    # clickPageAction() with `button: 1`: a middle click.
                    self.browser.click_view(head.wait_page_action_button(self, extension), button=2)
                else:
                    head.click_page_action(self, extension)
            else:
                self.next_test(extension, tab, other_tabs, value)

        extension.await_finish('pageaction-tests-done')

        extension.unload()

        self.check(head.page_action_button(self, extension) is None,
                   'pageAction image removed from document')

        self.check(head_pageAction.popup_view(self) is None,
                   'pageAction panel removed from document')

        self.browser.close_target(tab)

    def next_test(self, extension, tab, other_tabs, expecting):
        """The test's handler of the add-on's "next-test" message."""
        panel = head_pageAction.popup_targets(self, extension)
        if expecting.get('expectClosed'):
            self.check(panel, 'Expect panel to exist')
            head_pageAction.wait_popup_shown(self)

            extension.send_message('close-popup')

            head_pageAction.wait_popup_hidden(self, extension)
        elif expecting.get('closeOnTabSwitch'):
            self.check(panel, 'Expect panel to exist')
            head_pageAction.wait_popup_shown(self)

            others = [t['id'] for t in self.browser.targets() if t['id'] in other_tabs]
            self.check(others, 'Should have an inactive tab to switch to')

            if others:
                self.browser.browser_call('Target.activateTarget', targetId=others[0])
                head_pageAction.wait_popup_hidden(self, extension)

                self.browser.browser_call('Target.activateTarget', targetId=tab.id)
        elif panel:
            head_pageAction.wait_popup_shown(self)
            self.browser.close_target(Page(panel[0]))
            head_pageAction.wait_popup_hidden(self, extension)

        assert_view_count(self, extension, 1)

        if panel:
            self.check(head_pageAction.popup_view(self) is None,
                       'panel successfully removed from document after hiding')

        extension.send_message('next-test')

    def test_02_page_action_security(self):
        url = 'chrome://browser/content/browser.xhtml'

        apis = ['browser_action', 'page_action']

        for api in apis:
            extension = self.load_extension(
                manifest={
                    api: {'default_popup': url},
                },
            )

            try:
                extension.startup()
                refused = False
            except RuntimeError:
                refused = True
            self.check(refused, f'{api}: Manifest rejected')
            if not refused:
                extension.unload()
