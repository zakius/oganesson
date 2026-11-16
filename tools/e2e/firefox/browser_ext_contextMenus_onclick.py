"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_onclick.js.

extension.sendMessage() reaches the background and tab.html, as in Firefox,
and each takes the messages for its own page. A click with modifiers holds
the keys down around a real click (head.py's close_extension_context_menu())."""

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'

# Loaded both as a background script and a tab page.
TEST_SCRIPT = JS('''function testScript() {
  let page = location.pathname.includes("tab.html") ? "tab" : "background";
  let clickCounts = {
    old: 0,
    new: 0,
  };
  browser.contextMenus.onClicked.addListener(() => {
    // Async to give other onclick handlers a chance to fire.
    setTimeout(() => {
      browser.test.sendMessage("onClicked-fired", page);
    });
  });
  browser.test.onMessage.addListener((toPage, msg) => {
    if (toPage !== page) {
      return;
    }
    browser.test.log(`Received ${msg} for ${toPage}`);
    if (msg == "get-click-counts") {
      browser.test.sendMessage("click-counts", clickCounts);
    } else if (msg == "clear-click-counts") {
      clickCounts.old = clickCounts.new = 0;
      browser.test.sendMessage("next");
    } else if (msg == "create-with-onclick") {
      browser.contextMenus.create(
        {
          id: "iden",
          title: "tifier",
          onclick() {
            ++clickCounts.old;
            browser.test.log(
              `onclick fired for original onclick property in ${page}`
            );
          },
        },
        () => browser.test.sendMessage("next")
      );
    } else if (msg == "create-without-onclick") {
      browser.contextMenus.create(
        {
          id: "iden",
          title: "tifier",
        },
        () => browser.test.sendMessage("next")
      );
    } else if (msg == "update-without-onclick") {
      browser.contextMenus.update(
        "iden",
        {
          enabled: true, // Already enabled, so this does nothing.
        },
        () => browser.test.sendMessage("next")
      );
    } else if (msg == "update-with-onclick") {
      browser.contextMenus.update(
        "iden",
        {
          onclick() {
            ++clickCounts.new;
            browser.test.log(
              `onclick fired for updated onclick property in ${page}`
            );
          },
        },
        () => browser.test.sendMessage("next")
      );
    } else if (msg == "remove") {
      browser.contextMenus.remove("iden", () =>
        browser.test.sendMessage("next")
      );
    } else if (msg == "removeAll") {
      browser.contextMenus.removeAll(() => browser.test.sendMessage("next"));
    }
  });

  if (page == "background") {
    browser.test.log("Opening tab.html");
    browser.tabs.create({
      url: "tab.html",
      active: false, // To not interfere with the context menu tests.
    });
  } else {
    // Sanity check - the pages must be in the same process.
    let pages = browser.extension.getViews();
    browser.test.assertTrue(
      pages.includes(window),
      "Expected this tab to be an extension view"
    );
    pages = pages.filter(w => w !== window);
    browser.test.assertEq(
      pages[0],
      browser.extension.getBackgroundPage(),
      "Expected the other page to be a background page"
    );
    browser.test.sendMessage("tab.html ready");
  }
}''')


class ContextMenusOnclickTest(head.ContextMenuTest):

    def test_01(self):
        tab1 = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=TEST_SCRIPT,
            files={
                'tab.html': '<!DOCTYPE html><meta charset="utf-8"><script src="tab.js"></script>',
                'tab.js': TEST_SCRIPT,
            })
        extension.startup()
        extension.await_message('tab.html ready')

        def click_context_menu():
            # Using openContextMenu instead of openExtensionContextMenu because the
            # test extension has only one context menu item.
            extension_menu_root = head.open_context_menu(self, tab1)
            items = extension_menu_root.by_label('tifier')
            # A failure ends the test, as Firefox's click on a missing item does.
            self.assertEqual(len(items), 1, 'Expected one context menu item')
            head.close_extension_context_menu(self, items[0])
            # One of them is "tab", the other is "background".
            extension.await_message('onClicked-fired')
            extension.await_message('onClicked-fired')

        def get_counts(page):
            extension.send_message(page, 'get-click-counts')
            return extension.await_message('click-counts')

        def reset_counts():
            extension.send_message('tab', 'clear-click-counts')
            extension.send_message('background', 'clear-click-counts')
            extension.await_message('next')
            extension.await_message('next')

        # During this test, at most one "onclick" attribute is expected at any time.
        for page_one in ['background', 'tab']:
            for page_two in ['background', 'tab']:
                # Testing with the menu created by page_one and updated by page_two.
                extension.send_message(page_one, 'create-with-onclick')
                extension.await_message('next')

                # Test that update without onclick attribute does not clear the existing
                # onclick handler.
                extension.send_message(page_two, 'update-without-onclick')
                extension.await_message('next')
                click_context_menu()
                click_counts = get_counts(page_one)
                self.is_(click_counts['old'], 1,
                                 f'Original onclick should still be present in {page_one}')
                self.is_(click_counts['new'], 0,
                                 f'Not expecting any new handlers in {page_one}')
                if page_one != page_two:
                    click_counts = get_counts(page_two)
                    self.is_(click_counts['old'], 0,
                                     f'Not expecting any handlers in {page_two}')
                    self.is_(click_counts['new'], 0,
                                     f'Not expecting any new handlers in {page_two}')
                reset_counts()

                # Test that update with onclick handler in a different page clears the
                # existing handler and activates the new onclick handler.
                extension.send_message(page_two, 'update-with-onclick')
                extension.await_message('next')
                click_context_menu()
                click_counts = get_counts(page_one)
                self.is_(click_counts['old'], 0,
                                 f'Original onclick should be gone from {page_one}')
                if page_one != page_two:
                    self.is_(click_counts['new'], 0,
                                     f'Still not expecting new handlers in {page_one}')
                click_counts = get_counts(page_two)
                if page_one != page_two:
                    self.is_(click_counts['old'], 0,
                                     f'Not expecting an old onclick in {page_two}')
                self.is_(click_counts['new'], 1,
                                 f'New onclick should be triggered in {page_two}')
                reset_counts()

                # Test that updating the handler (different again from the last `update`
                # call, but the same as the `create` call) clears the existing handler
                # and activates the new onclick handler.
                extension.send_message(page_one, 'update-with-onclick')
                extension.await_message('next')
                click_context_menu()
                click_counts = get_counts(page_one)
                self.is_(click_counts['new'], 1,
                                 f'onclick should be triggered in {page_one}')
                if page_one != page_two:
                    click_counts = get_counts(page_two)
                    self.is_(click_counts['new'], 0,
                                     f'onclick should be gone from {page_two}')
                reset_counts()

                # Test that removing the context menu and recreating it with the same ID
                # (in a different context) does not leave behind any onclick handlers.
                extension.send_message(page_two, 'remove')
                extension.await_message('next')
                extension.send_message(page_two, 'create-without-onclick')
                extension.await_message('next')
                click_context_menu()
                click_counts = get_counts(page_one)
                self.is_(click_counts['new'], 0,
                                 f'Did not expect any click handlers in {page_one}')
                if page_one != page_two:
                    click_counts = get_counts(page_two)
                    self.is_(click_counts['new'], 0,
                                     f'Did not expect any click handlers in {page_two}')
                reset_counts()

                # Remove context menu for the next iteration of the test. And just to get
                # more coverage, let's use removeAll instead of remove.
                extension.send_message(page_one, 'removeAll')
                extension.await_message('next')
        extension.unload()
        self.browser.close_target(tab1)

    def test_onclick_modifiers(self):
        background = JS('''function background() {
            function onclick(info) {
              browser.test.sendMessage("click", info);
            }
            browser.contextMenus.create(
              { contexts: ["all"], title: "modify", onclick },
              () => {
                browser.test.sendMessage("ready");
              }
            );
          }''')

        extension = self.load_extension(manifest={'permissions': ['contextMenus']},
                                        background=background)
        tab = self.open_tab(PAGE)

        extension.startup()
        extension.await_message('ready')

        def click(modifiers=None):
            menu = head.open_context_menu(self, tab)
            items = menu.by_label('modify')
            self.assertEqual(len(items), 1, 'Got exactly one context menu item')
            head.close_extension_context_menu(self, items[0], modifiers)
            return extension.await_message('click')

        plain = click()
        self.is_(plain.get('modifiers'), [], 'modifiers array empty with a plain click')

        shift = click({'shiftKey': True})
        self.is_(','.join(shift.get('modifiers') or []), 'Shift', 'Correct modifier: Shift')

        ctrl = click({'ctrlKey': True})
        self.is_(','.join(ctrl.get('modifiers') or []), 'Ctrl', 'Correct modifier: Ctrl')

        alt_shift = click({'altKey': True, 'shiftKey': True})
        self.is_(','.join(sorted(alt_shift.get('modifiers') or [])), 'Alt,Shift',
                 'Correct modifiers: Shift+Alt')

        self.browser.close_target(tab)
        extension.unload()
