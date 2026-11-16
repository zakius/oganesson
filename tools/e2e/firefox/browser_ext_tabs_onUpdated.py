"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_tabs_onUpdated.js.

mochi.test:8888 is a local server here, with Firefox's
context_tabs_onUpdated_page.html and its frame, and a page at /. Left out:
the last task, forceGC(), a Gecko internal. The add-ons' code is Firefox's,
as it is."""

from extension_test_utils import JS, FirefoxTest
from firefox.head import DIR, close_window, open_new_browser_window

HTML = {'Content-Type': 'text/html'}
PAGE = b'''<html>
  <body>
    <h3>test page</h3>
    <iframe src="about:blank"></iframe>
    <script>
      "use strict";

      window.onmessage = function(evt) {
        if (evt.data === "updated-iframe-url") {
          window.postMessage("frame-updated", "*");
        }
      };
      window.onload = function() {
        document.querySelector("iframe").setAttribute("src", "context_tabs_onUpdated_iframe.html");
      };
    </script>
  </body>
</html>
'''
IFRAME = b'''<html>
  <body>
    <h3>test iframe</h3>
    <script>
      "use strict";

      window.onload = function() {
        window.onhashchange = function() {
          window.parent.postMessage("updated-iframe-url", "*");
        };
        // NOTE: without the this setTimeout the location change is not fired
        // even without the "fire only for top level windows" fix
        setTimeout(function() {
          window.location.hash = "updated-iframe-url";
        }, 0);
      };
    </script>
  </body>
</html>
'''


class TabsOnUpdatedTest(FirefoxTest):
    hosts = ('mochi.test',)
    routes = {
        '/': (200, HTML, b'<!DOCTYPE html><title>mochi.test</title><p>page'),
        f'{DIR}context_tabs_onUpdated_page.html': (200, HTML, PAGE),
        f'{DIR}context_tabs_onUpdated_iframe.html': (200, HTML, IFRAME),
    }

    def test_01_onUpdated_sequence(self):
        win1 = open_new_browser_window(self)

        extension = self.load_extension(
            manifest={
                'permissions': ['tabs'],
                'content_scripts': [
                    {
                        'matches': ['http://mochi.test/*/context_tabs_onUpdated_page.html'],
                        'js': ['content-script.js'],
                        'run_at': 'document_start',
                    },
                ],
            },
            background=JS('''function () {
      let pageURL =
        "http://mochi.test:8888/browser/browser/components/extensions/test/browser/context_tabs_onUpdated_page.html";

      let expectedSequence = [
        { status: "loading" },
        { status: "loading", url: pageURL },
        { status: "complete" },
      ];
      let collectedSequence = [];

      browser.tabs.onUpdated.addListener(function (tabId, updatedInfo) {
        // onUpdated also fires with updatedInfo.faviconUrl, so explicitly
        // check for updatedInfo.status before recording the event.
        if ("status" in updatedInfo) {
          collectedSequence.push(updatedInfo);
        }
      });

      browser.runtime.onMessage.addListener(function () {
        if (collectedSequence.length !== expectedSequence.length) {
          browser.test.assertEq(
            JSON.stringify(expectedSequence),
            JSON.stringify(collectedSequence),
            "got unexpected number of updateInfo data"
          );
        } else {
          for (let i = 0; i < expectedSequence.length; i++) {
            browser.test.assertEq(
              expectedSequence[i].status,
              collectedSequence[i].status,
              "check updatedInfo status"
            );
            if (expectedSequence[i].url || collectedSequence[i].url) {
              browser.test.assertEq(
                expectedSequence[i].url,
                collectedSequence[i].url,
                "check updatedInfo url"
              );
            }
          }
        }

        browser.test.notifyPass("tabs.onUpdated");
      });

      browser.tabs.create({ url: pageURL });
    }'''),
            files={
                'content-script.js': '''
        window.addEventListener("message", function(evt) {
          if (evt.data == "frame-updated") {
            browser.runtime.sendMessage("load-completed");
          }
        }, true);
      ''',
            })

        extension.startup()
        extension.await_finish('tabs.onUpdated')

        extension.unload()

        close_window(self, win1)

    def do_test_update(self, background, with_permissions=True):
        win1 = open_new_browser_window(self)

        manifest = {}
        if with_permissions:
            manifest['permissions'] = ['tabs', 'http://mochi.test/']
        extension = self.load_extension(manifest=manifest, background=background)

        extension.startup()
        extension.await_finish('finish')

        extension.unload()

        close_window(self, win1)

    def test_02_pinned(self):
        self.do_test_update(JS('''function background() {
    // Create a new tab for testing update.
    browser.tabs.create({}, function (tab) {
      browser.tabs.onUpdated.addListener(function onUpdated(tabId, changeInfo) {
        // Check callback
        browser.test.assertEq(tabId, tab.id, "Check tab id");
        browser.test.log("onUpdate: " + JSON.stringify(changeInfo));
        if ("pinned" in changeInfo) {
          browser.test.assertTrue(changeInfo.pinned, "Check changeInfo.pinned");
          browser.tabs.onUpdated.removeListener(onUpdated);
          // Remove created tab.
          browser.tabs.remove(tabId);
          browser.test.notifyPass("finish");
        }
      });
      browser.tabs.update(tab.id, { pinned: true });
    });
  }'''))

    def test_03_unpinned(self):
        self.do_test_update(JS('''function background() {
    // Create a new tab for testing update.
    browser.tabs.create({ pinned: true }, function (tab) {
      browser.tabs.onUpdated.addListener(function onUpdated(tabId, changeInfo) {
        // Check callback
        browser.test.assertEq(tabId, tab.id, "Check tab id");
        browser.test.log("onUpdate: " + JSON.stringify(changeInfo));
        if ("pinned" in changeInfo) {
          browser.test.assertFalse(
            changeInfo.pinned,
            "Check changeInfo.pinned"
          );
          browser.tabs.onUpdated.removeListener(onUpdated);
          // Remove created tab.
          browser.tabs.remove(tabId);
          browser.test.notifyPass("finish");
        }
      });
      browser.tabs.update(tab.id, { pinned: false });
    });
  }'''))

    def test_04_url(self):
        self.do_test_update(JS('''function background() {
    // Create a new tab for testing update.
    browser.tabs.create({ url: "about:blank?initial_url=1" }, function (tab) {
      const expectedUpdatedURL = "about:blank?updated_url=1";

      browser.tabs.onUpdated.addListener(function onUpdated(tabId, changeInfo) {
        // Wait for the tabs.onUpdated events related to the updated url (because
        // there is a good chance that we may still be receiving events related to
        // the browser.tabs.create API call above before we are able to start
        // loading the new url from the browser.tabs.update API call below).
        if ("url" in changeInfo && changeInfo.url === expectedUpdatedURL) {
          browser.test.assertEq(
            expectedUpdatedURL,
            changeInfo.url,
            "Got tabs.onUpdated event for the expected url"
          );
          browser.tabs.onUpdated.removeListener(onUpdated);
          // Remove created tab.
          browser.tabs.remove(tabId);
          browser.test.notifyPass("finish");
        }
        // Check callback
        browser.test.assertEq(tabId, tab.id, "Check tab id");
        browser.test.log("onUpdate: " + JSON.stringify(changeInfo));
      });

      browser.tabs.update(tab.id, { url: expectedUpdatedURL });
    });
  }'''))

    def test_05_title(self):
        self.do_test_update(JS('''async function background() {
    const url =
      "http://mochi.test:8888/browser/browser/components/extensions/test/browser/context_tabs_onUpdated_page.html";
    const tab = await browser.tabs.create({ url });

    browser.tabs.onUpdated.addListener(function onUpdated(tabId, changeInfo) {
      browser.test.assertEq(tabId, tab.id, "Check tab id");
      browser.test.log(`onUpdated: ${JSON.stringify(changeInfo)}`);
      if ("title" in changeInfo && changeInfo.title === "New Message (1)") {
        browser.test.log("changeInfo.title is correct");
        browser.tabs.onUpdated.removeListener(onUpdated);
        browser.tabs.remove(tabId);
        browser.test.notifyPass("finish");
      }
    });

    browser.tabs.executeScript(tab.id, {
      code: "document.title = 'New Message (1)'",
    });
  }'''))

    def test_06_without_tabs_permission(self):
        self.do_test_update(JS('''async function background() {
    const url =
      "http://mochi.test:8888/browser/browser/components/extensions/test/browser/context_tabs_onUpdated_page.html";
    let tab = null;
    let count = 0;

    browser.tabs.onUpdated.addListener(function onUpdated(tabId, changeInfo) {
      // An attention change can happen during tabs.create, so
      // we can't compare against tab yet.
      if (!("attention" in changeInfo)) {
        browser.test.assertEq(tabId, tab.id, "Check tab id");
      }
      browser.test.log(`onUpdated: ${JSON.stringify(changeInfo)}`);

      browser.test.assertFalse(
        "url" in changeInfo,
        "url should not be included without tabs permission"
      );
      browser.test.assertFalse(
        "favIconUrl" in changeInfo,
        "favIconUrl should not be included without tabs permission"
      );
      browser.test.assertFalse(
        "title" in changeInfo,
        "title should not be included without tabs permission"
      );

      if (changeInfo.status == "complete") {
        count++;
        if (count === 1) {
          browser.tabs.reload(tabId);
        } else {
          browser.test.log("Reload complete");
          browser.tabs.onUpdated.removeListener(onUpdated);
          browser.tabs.remove(tabId);
          browser.test.notifyPass("finish");
        }
      }
    });

    tab = await browser.tabs.create({ url });
  }'''), with_permissions=False)

    def test_07_onUpdated_after_onRemoved(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''async function background() {
      const url =
        "http://mochi.test:8888/browser/browser/components/extensions/test/browser/context_tabs_onUpdated_page.html";
      let removed = false;
      let tab;

      // If remove happens fast and we never receive onUpdated, that is ok, but
      // we never want to receive onUpdated after onRemoved.
      browser.tabs.onUpdated.addListener(function onUpdated(tabId) {
        if (!tab || tab.id !== tabId) {
          return;
        }
        browser.test.assertFalse(
          removed,
          "tab has not been removed before onUpdated"
        );
      });

      browser.tabs.onRemoved.addListener(tabId => {
        if (!tab || tab.id !== tabId) {
          return;
        }
        removed = true;
        browser.test.notifyPass("onRemoved");
      });

      tab = await browser.tabs.create({ url });
      browser.tabs.remove(tab.id);
    }'''))
        extension.startup()
        extension.await_finish('onRemoved')
        extension.unload()

    def test_08_pin_discarded_tab(self):
        # Regression test for Bug 1852391.
        extension = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''async function background() {
      const url = "http://mochi.test:8888";
      const newTab = await browser.tabs.create({
        url,
        active: false,
        discarded: true,
      });
      browser.tabs.onUpdated.addListener(
        async (tabId, changeInfo) => {
          browser.test.assertEq(
            tabId,
            newTab.id,
            "Expect onUpdated to be fired for the expected tab"
          );
          browser.test.assertEq(
            changeInfo.pinned,
            true,
            "Expect pinned to be set to true"
          );
          await browser.tabs.remove(newTab.id);
          browser.test.notifyPass("onPinned");
        },
        { properties: ["pinned"] }
      );
      await browser.tabs.update(newTab.id, { pinned: true }).catch(err => {
        browser.test.fail(`Got unexpected rejection from tabs.update: ${err}`);
        browser.test.notifyFail("onPinned");
      });
    }'''))

        extension.startup()
        extension.await_finish('onPinned')
        extension.unload()
