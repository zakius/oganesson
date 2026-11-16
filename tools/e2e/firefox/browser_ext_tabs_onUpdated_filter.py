"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_tabs_onUpdated_filter.js.

mochi.test:8888 is a local server here, with a page at / and an article at
/readerModeArticle.html. Firefox's containers 1 and 2 (userContextId) are
Personal and Work; this browser has the same two first, as
firefox-container-personal and firefox-container-work, so test_filter_cookieStoreId
filters on Work's ID and opens its tabs in Personal and Work as the user
does, from a link's "Open link in container" menu (add_tab())."""

import time

from extension_test_utils import JS, FirefoxTest
from harness import Page, wait_for

PAGE = (200, {'Content-Type': 'text/html'}, b'<!DOCTYPE html><title>mochi.test</title><p>page')
ARTICLE = (200, {'Content-Type': 'text/html'}, (
    b'<!DOCTYPE html><html><head><title>Article title</title></head><body><article>'
    b'<h1>Article title</h1>' + b'<p>' + b'Lorem ipsum dolor sit amet, consectetur adipiscing '
    b'elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. ' * 12 + b'</p>' * 1
    + b'</article></body></html>'))
CONTAINERS = {1: 'Personal', 2: 'Work'}


class TabsOnUpdatedFilterTest(FirefoxTest):
    hosts = ('mochi.test',)
    routes = {'/': PAGE, '/readerModeArticle.html': ARTICLE,
              '/links': (200, {'Content-Type': 'text/html'},
                         b'<!DOCTYPE html><a href="/never">link</a>'),
              '/never': lambda headers: time.sleep(60) or PAGE}

    def add_tab(self, url, user_context_id):
        """BrowserTestUtils.addTab(gBrowser, url, {userContextId}): a
        background tab at `url` in that container. The menu that opens a
        link in a container offers it for web pages only, so the link is to
        a page that never loads, and the tab goes on to `url`."""
        links = self.open_tab('http://mochi.test:8888/links')
        try:
            before = {t['id'] for t in self.browser.targets()}
            self.browser.click_element(links, 'a', button=3)
            for title in ('Open link in container', CONTAINERS[user_context_id]):
                self.browser.click_view(wait_for(
                    lambda title=title: next((i for menu in self.browser.menus() for group in menu
                                              for i in group if i['Title'] == title), None),
                    what=f'the menu item "{title}"'))
            target = wait_for(lambda: next((t for t in self.browser.targets()
                                            if t['id'] not in before and t['type'] == 'page'),
                                           None), what='the new tab')
        finally:
            self.browser.close_target(links)
        page = Page(target)
        page.call('Page.navigate', url=url)
        wait_for(lambda: page.eval('location.href') == url, what=f'{url} in the tab')
        return page

    def test_01_filter_url(self):
        ext_fail = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  browser.test.fail(
                    `received unexpected onUpdated event ${JSON.stringify(changeInfo)}`
                  );
                },
                { urls: ["*://*.mozilla.org/*"] }
              );
            }'''))
        ext_fail.startup()

        ext_perm = self.load_extension(
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                () => {
                  browser.test.fail(
                    `received unexpected onUpdated event without tabs permission`
                  );
                },
                { urls: ["*://mochi.test/*"] }
              );
            }'''))
        ext_perm.startup()

        ext_ok = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  browser.test.log(`got onUpdated ${JSON.stringify(changeInfo)}`);
                  if (changeInfo.status === "complete") {
                    browser.test.notifyPass("onUpdated");
                  }
                },
                { urls: ["*://mochi.test/*"] }
              );
            }'''))
        ext_ok.startup()

        tab = self.open_tab('http://mochi.test:8888/')
        ext_ok.await_finish('onUpdated')

        ext_ok.unload()
        ext_fail.unload()
        ext_perm.unload()

        self.browser.close_target(tab)

    def test_02_filter_url_activeTab(self):
        ext = self.load_extension(
            manifest={
                'permissions': ['activeTab'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                () => {
                  browser.test.fail(
                    "should only have notification for activeTab, selectedTab is not activeTab"
                  );
                },
                { urls: ["*://mochi.test/*"] }
              );
            }'''))
        ext.startup()

        ext2 = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  if (changeInfo.status === "complete") {
                    browser.test.notifyPass("onUpdated");
                  }
                },
                { urls: ["*://mochi.test/*"] }
              );
            }'''))
        ext2.startup()

        tab = self.open_tab('http://mochi.test:8888/#foreground')
        ext2.await_finish('onUpdated')

        ext.unload()
        ext2.unload()
        self.browser.close_target(tab)

    def test_03_filter_tabId(self):
        ext_fail = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  browser.test.fail(
                    `received unexpected onUpdated event ${JSON.stringify(changeInfo)}`
                  );
                },
                { tabId: 12345 }
              );
            }'''))
        ext_fail.startup()

        ext_ok = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener((tabId, changeInfo) => {
                if (changeInfo.status === "complete") {
                  browser.test.notifyPass("onUpdated");
                }
              });
            }'''))
        ext_ok.startup()

        ext_ok2 = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onCreated.addListener(tab => {
                browser.tabs.onUpdated.addListener(
                  (tabId, changeInfo) => {
                    if (changeInfo.status === "complete") {
                      browser.test.notifyPass("onUpdated");
                    }
                  },
                  { tabId: tab.id }
                );
                browser.test.log(`Tab specific tab listener on tab ${tab.id}`);
              });
            }'''))
        ext_ok2.startup()

        tab = self.open_tab('http://mochi.test:8888/')
        ext_ok.await_finish('onUpdated')
        ext_ok2.await_finish('onUpdated')

        ext_ok.unload()
        ext_ok2.unload()
        ext_fail.unload()

        self.browser.close_target(tab)

    def test_04_filter_windowId(self):
        ext_fail = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  browser.test.fail(
                    `received unexpected onUpdated event ${JSON.stringify(changeInfo)}`
                  );
                },
                { windowId: 12345 }
              );
            }'''))
        ext_fail.startup()

        ext_ok = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  if (changeInfo.status === "complete") {
                    browser.test.notifyPass("onUpdated");
                  }
                },
                { windowId: browser.windows.WINDOW_ID_CURRENT }
              );
            }'''))
        ext_ok.startup()

        ext_ok2 = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''async function() {
              let window = await browser.windows.getCurrent();
              browser.test.log(`Window specific tab listener on window ${window.id}`);
              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  if (changeInfo.status === "complete") {
                    browser.test.notifyPass("onUpdated");
                  }
                },
                { windowId: window.id }
              );
              browser.test.sendMessage("ready");
            }'''))
        ext_ok2.startup()
        ext_ok2.await_message('ready')

        tab = self.open_tab('http://mochi.test:8888/')
        ext_ok.await_finish('onUpdated')
        ext_ok2.await_finish('onUpdated')

        ext_ok.unload()
        ext_ok2.unload()
        ext_fail.unload()

        self.browser.close_target(tab)

    def test_05_filter_cookieStoreId(self):
        ext = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              browser.tabs.onUpdated.addListener(
                async (tabId, changeInfo) => {
                  if (changeInfo.status === "complete") {
                    const tab = await browser.tabs.get(tabId);
                    browser.test.sendMessage("onUpdated", tab);
                  }
                },
                { cookieStoreId: "firefox-container-work" }
              );
              browser.test.sendMessage("ready");
            }'''))
        ext.startup()
        ext.await_message('ready')

        tab1 = self.add_tab('about:blank?1', 1)
        tab2 = self.add_tab('about:blank?2', 2)

        triggered_tab = ext.await_message('onUpdated')
        self.assertEqual(triggered_tab['url'], 'about:blank?2',
                         'The tab with the correct URL was triggered.')
        self.assertEqual(triggered_tab['cookieStoreId'], 'firefox-container-work',
                         'The tab with the correct cookieStoreId was triggered.')

        self.browser.close_target(tab1)
        self.browser.close_target(tab2)
        ext.unload()

    def test_06_filter_isArticle(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''function() {
              // We expect only status updates, anything else is a failure.
              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  browser.test.log(`got onUpdated ${JSON.stringify(changeInfo)}`);
                  if ("isArticle" in changeInfo) {
                    browser.test.notifyPass("isArticle");
                  }
                },
                { properties: ["isArticle"] }
              );
            }'''))
        extension.startup()

        tab = self.open_tab('http://mochi.test:8888/readerModeArticle.html')
        extension.await_finish('isArticle')

        extension.unload()

        self.browser.close_target(tab)

    def test_07_filter_property(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['tabs'],
            },
            background=JS('''async function() {
              // We expect only status updates, anything else is a failure.
              let properties = new Set([
                "audible",
                "discarded",
                "favIconUrl",
                "hidden",
                "isArticle",
                "mutedInfo",
                "pinned",
                "sharingState",
                "title",
                "url",
              ]);

              // Test that updated only happens after created.
              let created = false;
              let tabIds = (await browser.tabs.query({})).map(t => t.id);
              browser.tabs.onCreated.addListener(tab => {
                created = tab.id;
              });

              browser.tabs.onUpdated.addListener(
                (tabId, changeInfo) => {
                  // ignore tabs created prior to extension startup
                  if (tabIds.includes(tabId)) {
                    return;
                  }
                  browser.test.assertEq(created, tabId, "tab created before updated");

                  browser.test.log(`got onUpdated ${JSON.stringify(changeInfo)}`);
                  browser.test.assertTrue(!!changeInfo.status, "changeInfo has status");
                  if (Object.keys(changeInfo).some(p => properties.has(p))) {
                    browser.test.fail(
                      `received unexpected onUpdated event ${JSON.stringify(
                        changeInfo
                      )}`
                    );
                  }
                  if (changeInfo.status === "complete") {
                    browser.test.notifyPass("onUpdated");
                  }
                },
                { properties: ["status"] }
              );
              browser.test.sendMessage("ready");
            }'''))
        extension.startup()
        extension.await_message('ready')

        tab = self.open_tab('http://mochi.test:8888/')
        extension.await_finish('onUpdated')

        extension.unload()

        self.browser.close_target(tab)
