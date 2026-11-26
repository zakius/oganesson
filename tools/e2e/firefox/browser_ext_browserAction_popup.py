"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_browserAction_popup.js.

The add-on's code is Firefox's, as it is. testInArea()'s areas are the
add-on pinned to the toolbar (CustomizableUI's navigation bar) or unpinned
into the Extensions menu (the add-ons panel), as the user does on its page in
chrome://extensions (head.pin_to_toolbar()). clickBrowserAction() is a real
click on the add-on's toolbar button, or on its row in the Extensions menu
that the toolbar's Extensions button opens, and its `button: 1` a middle
click there. closeBrowserAction() closes the add-on's popup page, and
Firefox's popup panel is the popup bubble here, Chromium's ExtensionPopup
(head_pageAction.popup_view()). getBrowserAction().triggerAction(window), the
Gecko-internal call that Firefox's `_execute_browser_action` shortcut makes,
is that shortcut here: the port binds it to Alt+Shift+J on
chrome://extensions, as the user does, and presses it, in the popup while
one is open. Firefox's count of the add-on's views (assertViewCount()) is
the count of its pages open in the browser, its DevTools targets.
"""

import json

from firefox import head, head_pageAction
from extension_test_utils import JS, FirefoxTest
from harness import Page, wait_for

TRIGGER_KEY = 'Alt+Shift+J'


def script_page(url):
    return (f'<html><head><meta charset="utf-8"><script src="{url}"></script></head>'
            f'<body>{url}</body></html>')


def assert_view_count(test, extension, count):
    """assertViewCount(): the add-on has `count` pages open."""
    prefix = f'chrome-extension://{extension.id}/'
    views = [t for t in test.browser.targets() if t['url'].startswith(prefix)]
    test.is_(len(views), count, 'Should have the expected number of extension views')


def bind_trigger_key(test, extension):
    """Binds the add-on's `_execute_browser_action` command, which Chromium
    gives every add-on with a browser action, to TRIGGER_KEY."""
    page = test.browser.new_tab('chrome://extensions')
    try:
        wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
        update = {'extensionId': extension.id, 'commandName': '_execute_browser_action',
                  'keybinding': TRIGGER_KEY}
        page.eval(f'chrome.developerPrivate.updateExtensionCommand({json.dumps(update)})')
    finally:
        test.browser.close_target(page)


def trigger_action(test):
    """getBrowserAction(extension).triggerAction(window): the add-on's
    shortcut. An open popup has the keyboard focus and passes the shortcut
    on; a window focused anew would close it first."""
    key = TRIGGER_KEY.lower()
    if head_pageAction.popup_view(test):
        test.browser.xdotool('key', key)
    else:
        test.browser.key(key)


def click_browser_action(test, extension, pinned, button=0):
    """clickBrowserAction(), with Firefox's `button` (0 left, 1 middle)."""
    if pinned:
        view = test.browser.toolbar_button(extension.id)
    else:
        head.open_extensions_panel(test)
        view = test.browser.wait_view('ExtensionsMenuButton', Text='Generated extension')
    test.browser.click_view(view, button=button + 1)


def close_browser_action(test, extension):
    """closeBrowserAction(): the add-on's popup closes."""
    for target in head_pageAction.popup_targets(test, extension):
        test.browser.close_target(Page(target))


class BrowserActionPopupTest(FirefoxTest):

    def run_in_area(self, pinned):
        """testInArea(), in the toolbar (`pinned`) or in the Extensions
        menu."""
        extension = self.load_extension(
            background=JS('''function () {
      let middleClickShowPopup = false;
      browser.browserAction.onClicked.addListener((tabs, info) => {
        browser.test.sendMessage("browserAction-onClicked");
        if (info.button === 1 && middleClickShowPopup) {
          browser.browserAction.openPopup();
        }
      });

      browser.test.onMessage.addListener(async msg => {
        if (msg.type === "setBrowserActionPopup") {
          let opts = { popup: msg.popup };
          if (msg.onCurrentWindowId) {
            let { id } = await browser.windows.getCurrent();
            opts = { ...opts, windowId: id };
          } else if (msg.onActiveTabId) {
            let [{ id }] = await browser.tabs.query({
              active: true,
              currentWindow: true,
            });
            opts = { ...opts, tabId: id };
          }
          await browser.browserAction.setPopup(opts);
          browser.test.sendMessage("setBrowserActionPopup:done");
        } else if (msg.type === "setMiddleClickShowPopup") {
          middleClickShowPopup = msg.show;
          browser.test.sendMessage("setMiddleClickShowPopup:done");
        }
      });

      browser.test.sendMessage("background-page-ready");
    }'''),
            manifest={
                'browser_action': {
                    'default_popup': 'popup-a.html',
                    'browser_style': True,
                },
            },

            files={
                'popup-a.html': script_page('popup-a.js'),
                'popup-a.js': JS('''function () {
        browser.test.onMessage.addListener(msg => {
          if (msg == "close-popup-using-window.close") {
            window.close();
          }
        });

        window.onload = () => {
          let color = window.getComputedStyle(document.body).color;
          browser.test.assertEq("rgb(34, 36, 38)", color);
          browser.test.sendMessage("from-popup", "popup-a");
        };
      }'''),

                'data/popup-b.html': script_page('popup-b.js'),
                'data/popup-b.js': JS('''function () {
        window.onload = () => {
          browser.test.sendMessage("from-popup", "popup-b");
        };
      }'''),

                'data/popup-c.html': script_page('popup-c.js'),
                'data/popup-c.js': JS('''function () {
        // Close the popup before the document is fully-loaded to make sure that
        // we handle this case sanely.
        browser.test.sendMessage("from-popup", "popup-c");
        window.close();
      }'''),
            })

        extension.startup()
        extension.await_message('background-page-ready')

        # Move the browserAction widget to the area targeted by this test.
        head.pin_to_toolbar(self, extension, pinned)
        bind_trigger_key(self, extension)

        def set_browser_action_popup(**opts):
            extension.send_message({'type': 'setBrowserActionPopup', **opts})
            extension.await_message('setBrowserActionPopup:done')

        def set_show_popup_on_middle_click(show):
            extension.send_message({'type': 'setMiddleClickShowPopup', 'show': show})
            extension.await_message('setMiddleClickShowPopup:done')

        def run_test(action_type, wait_for_popup_loaded=False, expect_popup=None,
                     expect_on_clicked=False, close_popup=False):
            if action_type == 'click':
                click_browser_action(self, extension, pinned)
            elif action_type == 'trigger':
                trigger_action(self)
            elif action_type == 'middleClick':
                click_browser_action(self, extension, pinned, button=1)

            if expect_on_clicked:
                extension.await_message('browserAction-onClicked')

            if expect_popup:
                self.is_(extension.await_message('from-popup'), expect_popup,
                         'expected popup opened')

            if wait_for_popup_loaded:
                head_pageAction.await_extension_panel(self, extension)

            if close_popup:
                close_browser_action(self, extension)
                head_pageAction.wait_popup_hidden(self, extension)
                assert_view_count(self, extension, 1)

        # Click browser action, expect popup "a".
        run_test('click', expect_popup='popup-a', close_popup=True)

        # Click browser action again, expect popup "a".
        run_test('click', expect_popup='popup-a', wait_for_popup_loaded=True, close_popup=True)

        # Call triggerAction, expect popup "a" again. Leave popup open.
        run_test('trigger', expect_popup='popup-a', wait_for_popup_loaded=True)

        assert_view_count(self, extension, 2)

        # Call triggerAction again. Expect remaining popup closed.
        trigger_action(self)

        head_pageAction.wait_popup_hidden(self, extension)
        assert_view_count(self, extension, 1)

        # Call triggerAction again. Expect popup "a" again.
        run_test('trigger', expect_popup='popup-a', close_popup=True)

        # Set popup to "c" and click browser action. Expect popup "c".
        set_browser_action_popup(popup='data/popup-c.html')

        run_test('click', expect_popup='popup-c')

        head_pageAction.wait_popup_hidden(self, extension)
        assert_view_count(self, extension, 1)

        # Set popup to "b" and click browser action. Expect popup "b".
        set_browser_action_popup(popup='data/popup-b.html')

        run_test('click', expect_popup='popup-b', close_popup=True)

        # Click browser action again, expect popup "b".
        run_test('click', expect_popup='popup-b', close_popup=True)

        # Middle-click browser action, expect an event only.
        set_show_popup_on_middle_click(False)

        run_test('middleClick', expect_on_clicked=True)

        # Middle-click browser action again, expect a click event then a popup.
        set_show_popup_on_middle_click(True)

        run_test('middleClick', expect_on_clicked=True, expect_popup='popup-b', close_popup=True)

        # Clear popup URL. Click browser action. Expect click event.
        set_browser_action_popup(popup='')

        run_test('click', expect_on_clicked=True)

        # Click browser action again. Expect another click event.
        run_test('click', expect_on_clicked=True)

        # Call triggerAction. Expect click event.
        run_test('trigger', expect_on_clicked=True)

        # Set window-specific popup to "b" and click browser action. Expect popup "b".
        set_browser_action_popup(popup='data/popup-b.html', onCurrentWindowId=True)

        run_test('click', expect_popup='popup-b', close_popup=True)

        # Set tab-specific popup to "a" and click browser action. Expect popup
        # "a", and leave open.
        set_browser_action_popup(popup='/popup-a.html', onActiveTabId=True)

        run_test('click', expect_popup='popup-a')
        assert_view_count(self, extension, 2)

        # Tell popup "a" to call window.close(). Expect popup closed.
        extension.send_message('close-popup-using-window.close')

        head_pageAction.wait_popup_hidden(self, extension)
        assert_view_count(self, extension, 1)

        # Unload the extension and verify that the browserAction widget is gone.
        extension.unload()

        # Firefox's widget keeps its popup's panel view in the document until
        # the add-on goes; here a popup's view goes when it closes, so the
        # add-on's toolbar button, named after it, is what has to go.
        def buttons():
            return [view for view in self.browser.views('ToolbarActionView') if view.visible
                    and (view['TooltipText'] or '').startswith('Generated extension')]
        try:
            wait_for(lambda: not buttons(), timeout=5, what="the add-on's toolbar button to go")
            gone = True
        except AssertionError:
            gone = False
        self.check(head_pageAction.popup_view(self) is None and gone,
                   'browserAction view removed from document')

    def test_01_browser_action_in_toolbar(self):
        self.run_in_area(pinned=True)

    def test_02_browser_action_in_panel(self):
        self.run_in_area(pinned=False)
