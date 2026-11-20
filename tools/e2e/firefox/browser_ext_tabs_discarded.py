"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_tabs_discarded.js.

The add-ons' code is Firefox's, as it is, but for the container's ID:
Firefox's first container, firefox-container-1, is Personal here,
firefox-container-personal. http://example.com/ and https://example.com/
are local servers here with the same pages: mochitest's index at /, whose
title is "mochitest index /", and a page with a link at /links.

The test's own steps make and read tabs through gBrowser and SessionStore,
which have no equal here. A helper add-on does them with the tabs API
instead (helper()):
- A lazy tab, BrowserTestUtils.addTab() with createLazyBrowser and its state
  set by SessionStore.setTabState() or lazyTabTitle, is a tab from the
  helper's tabs.create() with discarded and title (add_lazy_tab()): one
  history entry with the URL and the title, which loads when the tab is
  selected, as Firefox's lazy tab. test_discarded's tab is at
  http://example.com/ from the start, where Firefox's is at about:blank until
  setTabState().
- A tab's "pending" attribute is the helper's tab.discarded, and the
  userContextId of SessionStore.getTabState() is the helper's
  tab.cookieStoreId (find_tab()).
- BrowserTestUtils.switchTab() is the helper's tabs.update() with active,
  and BrowserTestUtils.removeTab() its tabs.remove().
- BrowserTestUtils.addTab() of a tab that loads, in the private window, is
  a middle click on a link to the URL there (add_tab()), which opens it in
  the background, as addTab() does.

test_discarded_private_tab_restored: the add-on starts before the private
window opens, as in the incognito ports: letting it into private windows
opens chrome://extensions, which would open in the private window.

Left out of test_update_discarded: the wait for TabBrowserInserted and the
console check that the lazy browser wasn't inserted early, both Gecko's
lazy browser internals. The port waits for the tab to load the new URL."""

import json
import tempfile
from pathlib import Path

from extension_test_utils import JS, FirefoxTest
from firefox import head
from harness import Server, wait_for
from test_browser_traffic import certificate

HTML = {'Content-Type': 'text/html'}
ROUTES = {
    '/': (200, HTML, b'<!DOCTYPE html><title>mochitest index /</title><p>index'),
    '/links': (200, HTML, b'<!DOCTYPE html><a href="about:blank">link</a>'),
}


class TabsDiscardedTest(FirefoxTest):
    # http://example.com/ is `server`, and https://example.com/ `https`: a
    # rule for each port, which Chromium's host resolver rules match with
    # the port too.
    hosts = ('example.com:80',)
    routes = ROUTES
    # Chromium's HTTPS-Upgrades would load http://example.com/ from
    # `https`.
    prefs = {'https_upgrades': {'policy': {'upgrades_enabled': False}}}

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-discarded-'))
        cls.https = Server(ROUTES, tls=certificate(cls.folder, 'example.com'))
        cls.host_rules = (f'MAP example.com:443 127.0.0.1:{cls.https.port}',)
        cls.browser_args = (*cls.browser_args, '--ignore-certificate-errors')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.https.stop()

    def start_helper(self, incognito=False):
        """Loads the helper add-on that makes and reads tabs for the test's
        own steps; with `incognito`, it sees private windows' tabs too."""
        self.helper_extension = self.load_extension(
            manifest={'permissions': ['tabs']}, background=JS('function() {}'),
            incognito_override='spanning' if incognito else None)
        self.helper_extension.startup()

    def helper(self, expression):
        """The value of `expression`, which uses browser.tabs, in the helper
        add-on's background, awaited."""
        page = self.browser.extension_background(self.helper_extension.id)
        try:
            return page.eval(expression, gesture=False)
        finally:
            page.close()

    def add_lazy_tab(self, url, title):
        """A lazy tab at `url` with `title`, which hasn't loaded; its ID."""
        properties = json.dumps({'url': url, 'discarded': True, 'title': title})
        return self.helper(f'browser.tabs.create({properties}).then(tab => tab.id)')

    def find_tab(self, url):
        """The tab at `url`, as the helper's tabs.query() gives it, once
        there is one."""
        expression = (f'browser.tabs.query({{}})'
                      f'.then(tabs => tabs.find(tab => tab.url == {json.dumps(url)}) || null)')
        return wait_for(lambda: self.helper(expression), what=f'a tab at {url}')

    def remove_tab(self, tab_id):
        self.helper(f'browser.tabs.remove({tab_id})')

    def add_tab(self, page, url):
        """BrowserTestUtils.addTab(gBrowser, url) in the window whose active
        tab is `page`: a middle click on a link to `url` in that tab, which
        opens it in a background tab."""
        self.load_url(page, 'http://example.com/links')
        page.eval(f'document.querySelector("a").href = {json.dumps(url)}')
        page.click('a', button='middle')

    def test_01_discarded(self):
        self.start_helper()
        extension = self.load_extension(
            manifest={
                'permissions': ['tabs', 'webNavigation'],
            },
            background=JS('''function() {
      browser.webNavigation.onCompleted.addListener(
        async details => {
          browser.test.log(`webNav onCompleted received for ${details.tabId}`);
          let updatedTab = await browser.tabs.get(details.tabId);
          browser.test.assertEq(
            false,
            updatedTab.discarded,
            "lazy to non-lazy update discard property"
          );
          browser.test.notifyPass("test-finished");
        },
        { url: [{ hostContains: "example.com" }] }
      );

      browser.tabs.onCreated.addListener(function (tab) {
        browser.test.assertEq(
          true,
          tab.discarded,
          "non-lazy tab onCreated discard property"
        );
        browser.tabs.update(tab.id, { active: true });
      });
    }'''))

        extension.startup()

        test_tab = self.add_lazy_tab('http://example.com/', 'Example Domain')

        extension.await_finish('test-finished')
        extension.unload()

        self.remove_tab(test_tab)
        self.helper_extension.unload()

    # Regression test for Bug 1819794.
    def test_02_create_discarded_with_cookieStoreId(self):
        self.start_helper()
        extension = self.load_extension(
            manifest={
                'permissions': ['contextualIdentities', 'cookies'],
            },
            background=JS('''async function() {
      const [{ cookieStoreId }] = await browser.contextualIdentities.query({});
      browser.test.assertEq(
        "firefox-container-personal",
        cookieStoreId,
        "Got expected cookieStoreId"
      );
      await browser.tabs.create({
        url: `http://example.com/#${cookieStoreId}`,
        cookieStoreId,
        discarded: true,
      });
      await browser.tabs.create({
        url: `http://example.com/#no-container`,
        discarded: true,
      });
    }'''),
            # Needed by ExtensionSettingsStore (as a side-effect of contextualIdentities permission).
            use_addon_manager='temporary')

        extension.startup()

        tab_container = self.find_tab('http://example.com/#firefox-container-personal')
        self.is_(tab_container['discarded'], True, 'new container tab should be discarded')
        self.is_(tab_container['cookieStoreId'], 'firefox-container-personal',
                 'Expect a userContextId associated to the new discarded container tab')

        tab_default = self.find_tab('http://example.com/#no-container')
        self.is_(tab_default['discarded'], True, 'new non-container tab should be discarded')
        self.is_(tab_default['cookieStoreId'], 'firefox-default',
                 'Expect userContextId 0 associated to the new discarded non-container tab')

        self.remove_tab(tab_container['id'])
        self.remove_tab(tab_default['id'])
        extension.unload()
        self.helper_extension.unload()

    # If discard is called immediately after creating a new tab, the new tab may not have loaded,
    # and the sessionstore for that tab is not ready for discarding.  The result was a corrupted
    # sessionstore for the tab, which when the tab was activated, resulted in a tab with partial
    # state.
    def test_03_create_then_discard(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['tabs', 'webNavigation'],
            },
            background=JS('''async function() {
      let createdTab;

      browser.tabs.onUpdated.addListener((tabId, updatedInfo) => {
        if (!updatedInfo.discarded) {
          return;
        }

        browser.webNavigation.onCompleted.addListener(
          async details => {
            browser.test.assertEq(
              createdTab.id,
              details.tabId,
              "created tab navigation is completed"
            );
            let activeTab = await browser.tabs.get(details.tabId);
            browser.test.assertEq(
              "http://example.com/",
              details.url,
              "created tab url is correct"
            );
            browser.test.assertEq(
              "http://example.com/",
              activeTab.url,
              "created tab url is correct"
            );
            browser.tabs.remove(details.tabId);
            browser.test.notifyPass("test-finished");
          },
          { url: [{ hostContains: "example.com" }] }
        );

        browser.tabs.update(tabId, { active: true });
      });

      createdTab = await browser.tabs.create({
        url: "http://example.com/",
        active: false,
      });
      browser.tabs.discard(createdTab.id);
    }'''))
        extension.startup()
        extension.await_finish('test-finished')
        extension.unload()

    def test_04_create_discarded(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['tabs', 'webNavigation'],
            },
            background=JS('''function() {
      let tabOpts = {
        url: "http://example.com/",
        active: false,
        discarded: true,
        title: "discarded tab",
      };

      browser.webNavigation.onCompleted.addListener(
        async details => {
          let activeTab = await browser.tabs.get(details.tabId);
          browser.test.assertEq(
            tabOpts.url,
            activeTab.url,
            "restored tab url matches active tab url"
          );
          browser.test.assertEq(
            "mochitest index /",
            activeTab.title,
            "restored tab title is correct"
          );
          browser.tabs.remove(details.tabId);
          browser.test.notifyPass("test-finished");
        },
        { url: [{ hostContains: "example.com" }] }
      );

      browser.tabs.onCreated.addListener(tab => {
        browser.test.assertEq(
          tabOpts.active,
          tab.active,
          "lazy tab is not active"
        );
        browser.test.assertEq(
          tabOpts.discarded,
          tab.discarded,
          "lazy tab is discarded"
        );
        browser.test.assertEq(tabOpts.url, tab.url, "lazy tab url is correct");
        browser.test.assertEq(
          tabOpts.title,
          tab.title,
          "lazy tab title is correct"
        );
        browser.tabs.update(tab.id, { active: true });
      });

      browser.tabs.create(tabOpts);
    }'''))
        extension.startup()
        extension.await_finish('test-finished')
        extension.unload()

    def test_05_discarded_private_tab_restored(self):
        self.start_helper(incognito=True)
        extension = self.load_extension(
            incognito_override='spanning',
            background=JS('''function() {
      let isDiscarding = false;
      browser.tabs.onUpdated.addListener(
        async function listener(tabId, changeInfo, tab) {
          const { active, discarded, incognito } = tab;
          if (!incognito || active || discarded || isDiscarding) {
            return;
          }
          // Remove the onUpdated listener to prevent intermittent failure
          // to be hit if the listener gets called again for unrelated
          // tabs.onUpdated events that may get fired after the test case got
          // the tab-discarded test message that was expecting.
          isDiscarding = true;
          browser.tabs.onUpdated.removeListener(listener);
          browser.test.log(
            `Test extension discarding ${tabId}: ${JSON.stringify(changeInfo)}`
          );
          await browser.tabs.discard(tabId);
          browser.test.sendMessage("tab-discarded");
        },
        { properties: ["status"] }
      );
    }'''))

        extension.startup()

        # Open a private browsing window.
        private_page = head.open_private_window(self)
        private_win = head.window_of(self, private_page)

        self.add_tab(private_page, 'https://example.com/')
        extension.await_message('tab-discarded')
        new_tab = self.find_tab('https://example.com/')
        self.is_(new_tab['discarded'], True, 'private tab should be discarded')

        # Switching to the discarded background tab.
        self.helper(f'browser.tabs.update({new_tab["id"]}, {{active: true}})')

        # Wait for the restored tab to complete loading.
        loaded = wait_for(lambda: self.helper(
            f'browser.tabs.query({{}}).then(tabs => tabs.find(tab => tab.id == {new_tab["id"]}'
            ' && tab.status == "complete") || null)'), what='the restored tab to load')
        self.is_(loaded['discarded'], False, 'discarded private tab should have been restored')

        self.is_(loaded['url'], 'https://example.com/', 'Got the expected url on the restored tab')

        extension.unload()
        head.close_window(self, private_win)
        self.helper_extension.unload()

    def test_06_update_discarded(self):
        self.start_helper()
        extension = self.load_extension(
            manifest={
                'permissions': ['tabs', '<all_urls>'],
            },
            background=JS('''function() {
      browser.test.onMessage.addListener(async msg => {
        let [tab] = await browser.tabs.query({ url: "http://example.com/" });
        if (msg == "update") {
          await browser.tabs.update(tab.id, { url: "https://example.com/" });
        } else {
          browser.test.fail(`Unexpected message received: ${msg}`);
        }
      });
      browser.test.sendMessage("ready");
    }'''))

        extension.startup()
        extension.await_message('ready')

        lazy_tab = self.add_lazy_tab('http://example.com/', 'Example Domain')

        extension.send_message('update')

        wait_for(lambda: self.helper(
            f'browser.tabs.get({lazy_tab}).then(tab => tab.url == "https://example.com/"'
            ' && tab.status == "complete")'), what='the tab to load https://example.com/')

        self.remove_tab(lazy_tab)

        extension.unload()
        self.helper_extension.unload()
