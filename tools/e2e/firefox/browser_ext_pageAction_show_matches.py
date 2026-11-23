"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_show_matches.js.

The add-ons' code is Firefox's, as it is. example.com and mochi.test:8888 are
a local server here. Firefox's base tab, about:about, is this browser's page
of its own pages, chrome://about. check() reads the page action's button in
the location bar (head.page_action_button()), which shows where the page
action is shown: it waits a moment for the button to come or go, as Firefox's
promiseAnimationFrame() lets the location bar update. getId() is the tabs
API's ID, which the test asks the add-on's background for through DevTools:
the selected tab's (head.active_tab_id()), and in test_02 the tab before the
selected one, which the test opened just before it. There, `urls[j]` is
undefined in Firefox for the third column of `shown`, so its tabs open
about:blank. navigateTab() loads the URL in the tab again, a new document.

Left out: PromiseTestUtils.allowMatchingRejectionsGlobally(/packaging
errors/), which keeps Firefox's test harness from failing on the add-on that
doesn't load, a Gecko internal, and test_pageAction_restrictScheme_false,
which checks that a privileged add-on (Mozilla's own, with the
`mozillaAddons` permission) shows its page action on Firefox's reader view
(`about:reader`), a Gecko internal.
"""

from firefox import head
from extension_test_utils import JS, FirefoxTest
from harness import wait_for

PAGE = (200, {'Content-Type': 'text/html'}, b'<!DOCTYPE html><title>page</title><p>page')

# Each add-on's background: Firefox's getExtension(), as it is.
BACKGROUND = JS('''function () {
      browser.test.onMessage.addListener(
        async ({ method, param, expect, msg }) => {
          let result = await browser.pageAction[method](param);
          if (expect !== undefined) {
            browser.test.assertEq(expect, result, msg);
          }
          browser.test.sendMessage("done");
        }
      );
    }''')

TESTS = [
    {
        'name': 'Test shown for all_urls',
        'page_action': {
            'show_matches': ['<all_urls>'],
        },
        'shown': [True, True, False],
    },
    {
        'name': 'Test hide_matches overrides all_urls.',
        'page_action': {
            'show_matches': ['<all_urls>'],
            'hide_matches': ['*://mochi.test/*'],
        },
        'shown': [True, False, False],
    },
    {
        'name': 'Test shown only for show_matches.',
        'page_action': {
            'show_matches': ['*://mochi.test/*'],
        },
        'shown': [False, True, False],
    },
]

# For some reason about:about used to behave differently (maybe because only
# the latter is privileged?) so should be tested.  about:about is used in the
# test as the base tab.
URLS = ['http://example.com/', 'http://mochi.test:8888/']


class PageActionShowMatchesTest(FirefoxTest):
    hosts = ('example.com', 'mochi.test')
    routes = {'/': PAGE}

    def get_extension(self, page_action):
        return self.load_extension(manifest={'page_action': page_action},
                                   background=BACKGROUND)

    def send_message(self, ext, method, param, expect=None, msg=None):
        """sendMessage(): the add-on calls pageAction[method](param), and
        checks the result where the test expects one."""
        message = {'method': method, 'param': param}
        if expect is not None:
            message['expect'] = expect
        if msg is not None:
            message['msg'] = msg
        ext.send_message(message)
        ext.await_message('done')

    def switch_tab(self, tab):
        """BrowserTestUtils.switchTab()."""
        self.browser.browser_call('Target.activateTarget', targetId=tab.id)
        wait_for(lambda: tab.eval('document.visibilityState', gesture=False) == 'visible',
                 what='the tab to be selected')

    def navigate_tab(self, tab, url):
        """navigateTab(): the tab loads `url`, a new document, also where
        the tab is at `url` already."""
        tab.eval('window.__fxtestOldDocument = true')
        tab.call('Page.navigate', url=url)

        def loaded():
            try:
                return tab.eval('!window.__fxtestOldDocument && location.href == '
                                f'{url!r} && document.readyState == "complete"')
            except (AssertionError, RuntimeError):
                return False
        wait_for(loaded, what=f'{url} to load')

    def selected_tab_id(self, extension):
        """getId() of the selected tab."""
        return head.active_tab_id(self, extension)

    def tab_id_before_selected(self, extension):
        """getId() of the tab before the selected one in its window."""
        page = self.browser.extension_background(extension.id)
        try:
            return page.eval(
                'chrome.tabs.query({active: true, lastFocusedWindow: true})'
                '.then(([tab]) => chrome.tabs.query({windowId: tab.windowId, index: tab.index - 1}))'
                '.then(tabs => tabs[0].id)', gesture=False)
        finally:
            page.close()

    def check_shown(self, extension, tab, expected, msg):
        """check(): the page action's button shows in the location bar of
        `tab`, the selected tab, where `expected`, and pageAction.isShown()
        gives `expected`."""
        self.check(tab.eval('document.visibilityState', gesture=False) == 'visible',
                   f'tab {head.tab_location(tab)} is selected')

        def as_expected():
            return (head.page_action_button(self, extension) is not None) == expected
        try:
            wait_for(as_expected, timeout=2, what='the page action button')
        except AssertionError:
            pass
        # Sometimes we're hidden, sometimes a parent is hidden via css (e.g. about pages)
        hidden = head.page_action_button(self, extension) is None
        self.is_(not hidden, expected, msg + ' (computed)')
        self.send_message(extension, 'isShown', {'tabId': self.selected_tab_id(extension)},
                          expected, msg + ' (isShown)')

    def test_01_pageAction_default_show_tabs(self):
        # Check show_matches and hide_matches are respected when opening a new
        # tab or switching to an existing tab.
        switch_tab = self.open_tab('chrome://about')
        for i, test in enumerate(TESTS):
            # test ${i}: ${test.name}
            extension = self.get_extension(test['page_action'])
            extension.startup()
            for j, url in enumerate(URLS):
                expected = test['shown'][j]
                msg = (f'test {i} url {j}: page action is '
                       f'{"shown" if expected else "hidden"} for {url}')

                # Check new tab.
                tab = self.open_tab(url)
                self.check_shown(extension, tab, expected, msg + ' (new)')

                # Check switched tab.
                self.switch_tab(switch_tab)
                self.check_shown(extension, switch_tab, False, msg + ' (about:about)')
                self.switch_tab(tab)
                self.check_shown(extension, tab, expected, msg + ' (switched)')

                self.browser.close_target(tab)
            extension.unload()
        self.browser.close_target(switch_tab)

    def test_02_pageAction_default_show_install(self):
        # Check show_matches and hide_matches are respected when installing
        # the extension
        for i, test in enumerate(TESTS):
            # test ${i}: ${test.name}
            for expected in (True, False):
                if expected not in test['shown']:
                    continue
                j = test['shown'].index(expected)
                # urls[j], undefined in Firefox past the two URLs: a new tab
                # at about:blank.
                url = URLS[j] if j < len(URLS) else None
                initial_tab = self.open_tab(url or 'about:blank')
                install_tab = self.open_tab(url or 'about:blank')
                extension = self.get_extension(test['page_action'])
                extension.startup()
                msg = (f'test {i} url {j}: page action is '
                       f'{"shown" if expected else "hidden"} for {url or "undefined"}')
                self.check_shown(extension, install_tab, expected, msg + ' (active)')

                # initialTab has not been activated after installation, so we
                # have not evaluated whether the page action should be shown
                # in it. Check that pageAction.isShown works anyways.
                self.send_message(extension, 'isShown',
                                  {'tabId': self.tab_id_before_selected(extension)},
                                  expected, msg + ' (inactive)')

                self.browser.close_target(initial_tab)
                self.browser.close_target(install_tab)
                extension.unload()

    def test_03_pageAction_history(self):
        # Check match patterns are reevaluated when using history.pushState or
        # navigating
        url1 = 'http://example.com/'
        url2 = url1 + 'path/'
        extension = self.get_extension({
            'show_matches': [url1],
            'hide_matches': [url2],
        })
        extension.startup()
        tab = self.open_tab(url1)
        self.check_shown(extension, tab, True, 'page action is shown for ' + url1)
        tab_id = self.selected_tab_id(extension)

        # Use history.pushState to change the URL without navigating
        head.history_push_state(tab, url2)
        self.check_shown(extension, tab, False, 'page action is hidden for ' + url2)

        # Use hide()
        self.send_message(extension, 'hide', tab_id)
        self.check_shown(extension, tab, False, 'page action is still hidden')

        # Use history.pushState to revert to first url
        head.history_push_state(tab, url1)
        self.check_shown(extension, tab, False,
                         'hide() has more precedence than pattern matching')

        # Select another tab
        tab2 = self.open_tab(url1)

        # Perform navigation in the old tab
        self.navigate_tab(tab, url1)
        self.send_message(extension, 'isShown', {'tabId': tab_id}, True,
                          'Navigating undoes hide(), even when the tab is not selected.')

        self.browser.close_target(tab)
        self.browser.close_target(tab2)
        extension.unload()

    def test_04_pageAction_all_urls(self):
        # Check <all_urls> is not allowed in hide_matches
        extension = self.get_extension({
            'show_matches': ['*://mochi.test/*'],
            'hide_matches': ['<all_urls>'],
        })
        try:
            extension.startup()
            rejects = False
        except RuntimeError:
            rejects = True
        self.is_(rejects, True, 'startup failed')
