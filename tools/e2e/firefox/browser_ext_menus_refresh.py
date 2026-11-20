"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_refresh.js.

Firefox's getXULElementByMenuId() finds an item of the add-on by its element
ID, also in a closed submenu. Here the port reads the open menu
(menu_item()): an item by its label, as each item's label tells which it is,
in the menu or in the add-on's submenu, which it opens, and none while no
menu is open. An item's `disabled` attribute is its view's `Enabled`. A
check before a read of the item's label ends the test when the item is
missing, as Firefox's getAttribute() on null does. Firefox's Tools menu is
the app menu's More tools (head.open_tools_menu()), where an add-on's
`tools_menu` items are to show (zakius/oganesson#98).
"""

from firefox import head
from extension_test_utils import JS
from harness import wait_for

PAGE = f'{head.BASE}context.html'


class MenusRefreshTest(head.ContextMenuTest):

    def load_extension_with_menus_api(self):
        """loadExtensionWithMenusApi(): its callMenuApi() is call_menu_api(),
        and removeOnShownListener() is
        call_menu_api(extension, '* remove onShown listener')."""
        return self.load_extension(
            background=JS('''async function background() {
              function shownHandler() {
                browser.test.sendMessage("onShown fired");
              }

              browser.menus.onShown.addListener(shownHandler);
              browser.test.onMessage.addListener((method, ...params) => {
                let result;
                if (method === "* remove onShown listener") {
                  browser.menus.onShown.removeListener(shownHandler);
                  result = Promise.resolve();
                } else if (method === "create") {
                  result = new Promise(resolve => {
                    browser.menus.create(params[0], resolve);
                  });
                } else {
                  result = browser.menus[method](...params);
                }
                result.then(() => {
                  browser.test.sendMessage(`${method}-result`);
                });
              });
            }'''),
            manifest={
                'browser_action': {
                    'default_area': 'navbar',
                },
                'permissions': ['menus'],
            })

    def call_menu_api(self, extension, method, *params):
        extension.send_message(method, *params)
        return extension.await_message(f'{method}-result')

    def menu_item(self, label):
        """The open menu's item labelled `label`, in the menu or in the
        add-on's submenu, or None."""
        menus = self.browser.menus()
        if not menus:
            return None
        items = [item for group in menus[0] for item in group]
        if len(menus) > 1:
            items += [item for group in menus[1] for item in group]
        else:
            submenu = [item for item in items if head.label_of(item) == 'Generated extension'
                       and head.has_submenu(self, item)]
            if submenu:
                items += head.open_submenu(self, submenu[0]).items
        return next((item for item in items if head.label_of(item) == label), None)

    def expect_label(self, label, message):
        """is(elem.getAttribute("label"), label, message), which ends the
        test when there is no such item."""
        item = self.menu_item(label)
        self.assertIsNotNone(item, f'{message}: an item labelled {label!r}')
        return item

    def refresh_menus_while_visible(self, contexts, open_menu, close_menu):
        """testRefreshMenusWhileVisible()."""
        extension = self.load_extension_with_menus_api()
        extension.startup()
        self.call_menu_api(extension, 'create', {
            'id': 'abc',
            'title': 'first',
            'contexts': contexts,
        })
        self.is_(self.menu_item('first'), None, 'Menu item should not be visible')

        # Refresh before a menu is shown - should be noop.
        self.call_menu_api(extension, 'refresh')
        self.is_(self.menu_item('first'), None, 'Menu item should still not be visible')

        # Open menu and expect menu to be rendered.
        open_menu(extension)
        self.expect_label('first', 'expected label')

        extension.await_message('onShown fired')

        # Add new menus, but don't expect them to be rendered yet.
        self.call_menu_api(extension, 'update', 'abc', {'title': 'updated first'})
        self.call_menu_api(extension, 'create', {
            'id': 'def',
            'title': 'second',
            'contexts': contexts,
        })

        self.expect_label('first', 'expected unchanged label')
        self.is_(self.menu_item('second'), None, 'Second menu item should not be visible')

        # Refresh while a menu is shown - should be updated.
        self.call_menu_api(extension, 'refresh')

        self.expect_label('updated first', 'expected updated label')
        self.expect_label('second', 'expected second label')

        # Update the two menu items again.
        self.call_menu_api(extension, 'update', 'abc', {'enabled': False})
        self.call_menu_api(extension, 'update', 'def', {'enabled': False})
        self.call_menu_api(extension, 'refresh')
        elem = self.expect_label('updated first', 'the first menu item')
        self.is_(elem['Enabled'], 'false', '1st menu item should be disabled')
        elem = self.expect_label('second', 'the second menu item')
        self.is_(elem['Enabled'], 'false', '2nd menu item should be disabled')

        # Remove one.
        self.call_menu_api(extension, 'remove', 'abc')
        self.call_menu_api(extension, 'refresh')
        self.expect_label('second', 'other menu item should exist')
        self.is_(self.menu_item('updated first'), None, 'removed menu item should be gone')

        # Remove the last one.
        self.call_menu_api(extension, 'removeAll')
        self.call_menu_api(extension, 'refresh')
        self.is_(self.menu_item('second'), None, 'all menu items should be gone')

        # At this point all menu items have been removed. Create a new menu item so
        # we can confirm that browser.menus.refresh() does not render the menu item
        # after the menu has been hidden.
        self.call_menu_api(extension, 'create', {
            # The menu item with ID "abc" was removed before, so re-using the ID should
            # not cause any issues:
            'id': 'abc',
            'title': 're-used',
            'contexts': contexts,
        })
        self.call_menu_api(extension, 'refresh')
        self.expect_label('re-used', 'menu item should be created')

        close_menu()

        self.is_(self.menu_item('re-used'), None, 'menu item must be gone')

        # Refresh after menu was hidden - should be noop.
        self.call_menu_api(extension, 'refresh')
        self.is_(self.menu_item('re-used'), None, 'menu item must still be gone')

        extension.unload()

    # Check that one extension calling refresh() doesn't interfere with others.
    # When expectOtherItems == false, the other extension's menu items should not
    # show at all (e.g. for browserAction).
    def refresh_other(self, contexts, open_menu, close_menu, expect_other_items):
        """testRefreshOther()."""
        extension = self.load_extension_with_menus_api()
        other_extension = self.load_extension_with_menus_api()
        extension.startup()
        other_extension.startup()

        self.call_menu_api(extension, 'create', {
            'id': 'action_item',
            'title': 'visible menu item',
            'contexts': contexts,
        })

        self.call_menu_api(other_extension, 'create', {
            'id': 'action_item',
            'title': 'other menu item',
            'contexts': contexts,
        })

        open_menu(extension)
        extension.await_message('onShown fired')
        if expect_other_items:
            other_extension.await_message('onShown fired')

        self.expect_label('visible menu item', 'extension menu shown')
        if expect_other_items:
            self.expect_label('other menu item', "other extension's menu is also shown")
        else:
            self.is_(self.menu_item('other menu item'), None,
                     "other extension's menu should be hidden")

        self.call_menu_api(extension, 'update', 'action_item', {'title': 'changed'})
        self.call_menu_api(other_extension, 'update', 'action_item', {'title': 'foo'})
        self.call_menu_api(other_extension, 'refresh')

        # refreshing the menu of an unrelated extension should not affect the menu
        # of another extension.
        self.expect_label('visible menu item', 'extension menu shown')
        if expect_other_items:
            self.expect_label('foo', "other extension's item is updated")
        else:
            self.is_(self.menu_item('foo'), None,
                     "other extension's menu should still be hidden")

        close_menu()
        extension.unload()
        other_extension.unload()

    def close_menu(self):
        head.close_context_menu(self)
        wait_for(lambda: not self.browser.menus(), what='the menu to close')

    def test_01_refresh_menus_with_browser_action(self):
        args = {
            'contexts': ['browser_action'],
            'open_menu': lambda extension: head.open_action_context_menu(self, extension,
                                                                         'browser'),
            'close_menu': self.close_menu,
        }
        self.refresh_menus_while_visible(**args)
        self.refresh_other(**args, expect_other_items=False)

    def test_02_refresh_menus_with_tab(self):
        tab = self.open_tab(PAGE)
        args = {
            'contexts': ['tab'],
            'open_menu': lambda extension: head.open_tab_context_menu(self),
            'close_menu': self.close_menu,
        }
        self.refresh_menus_while_visible(**args)
        self.refresh_other(**args, expect_other_items=True)
        self.browser.close_target(tab)

    def test_03_refresh_menus_with_tools_menu(self):
        args = {
            'contexts': ['tools_menu'],
            'open_menu': lambda extension: head.open_tools_menu(self),
            'close_menu': self.close_menu,
        }
        self.refresh_menus_while_visible(**args)
        self.refresh_other(**args, expect_other_items=True)

    def test_04_refresh_menus_with_page(self):
        tab = self.open_tab(PAGE)
        args = {
            'contexts': ['page'],
            'open_menu': lambda extension: head.open_context_menu(self, tab, 'body'),
            'close_menu': self.close_menu,
        }
        self.refresh_menus_while_visible(**args)
        self.refresh_other(**args, expect_other_items=True)
        self.browser.close_target(tab)

    def test_05_refresh_without_menus_at_onShown(self):
        tab = self.open_tab(PAGE)
        extension = self.load_extension_with_menus_api()
        extension.startup()

        def do_open_menu():
            head.open_context_menu(self, tab, 'body')

        do_open_menu()
        extension.await_message('onShown fired')
        self.call_menu_api(extension, 'create', {
            'id': 'too late',
            'title': 'created after shown',
        })
        self.call_menu_api(extension, 'refresh')
        self.expect_label('created after shown',
                          'extension without visible menu items can add new items')

        self.call_menu_api(extension, 'update', 'too late', {'title': 'the menu item'})
        self.call_menu_api(extension, 'refresh')
        self.expect_label('the menu item', 'label should change')

        # The previously created menu item should be visible if the menu is closed
        # and re-opened.
        self.close_menu()
        do_open_menu()
        extension.await_message('onShown fired')
        self.expect_label('the menu item', 'previously registered item')
        self.close_menu()

        extension.unload()
        self.browser.close_target(tab)

    def test_06_refresh_without_onShown(self):
        tab = self.open_tab(PAGE)
        extension = self.load_extension_with_menus_api()
        extension.startup()
        self.call_menu_api(extension, '* remove onShown listener')

        head.open_context_menu(self, tab, 'body')
        self.call_menu_api(extension, 'create', {
            'id': 'too late',
            'title': 'created after shown',
        })

        self.is_(self.menu_item('created after shown'), None,
                 'item created after shown is not visible before refresh')

        self.call_menu_api(extension, 'refresh')
        self.expect_label('created after shown', 'refresh updates the menu even without onShown')

        self.close_menu()
        extension.unload()
        self.browser.close_target(tab)

    def test_07_refresh_menus_during_navigation(self):
        tab = self.open_tab(PAGE + '?1')
        extension = self.load_extension_with_menus_api()
        extension.startup()

        self.call_menu_api(extension, 'create', {
            'id': 'item1',
            'title': 'item1',
            'contexts': ['browser_action'],
            'documentUrlPatterns': ['*://*/*?1*'],
        })

        self.call_menu_api(extension, 'create', {
            'id': 'item2',
            'title': 'item2',
            'contexts': ['browser_action'],
            'documentUrlPatterns': ['*://*/*?2*'],
        })

        head.open_action_context_menu(self, extension, 'browser')
        extension.await_message('onShown fired')

        self.expect_label('item1', 'menu item 1 should be shown')
        self.is_(self.menu_item('item2'), None, 'menu item 2 should be hidden')

        tab.eval(f'location.href = {PAGE + "?2"!r}')
        wait_for(lambda: tab.eval('location.search + document.readyState', gesture=False)
                 == '?2complete', what='the page to load')

        self.call_menu_api(extension, 'refresh')

        # The menu items in a context menu are based on the context at the time of
        # opening the menu. Menus are not updated if the context changes, e.g. as a
        # result of navigation events after the menu was shown.
        # So when refresh() is called during the onShown event, then the original
        # URL (before navigation) should be used to determine whether to show a
        # URL-specific menu item, and NOT the current URL (after navigation).
        self.expect_label('item1', 'menu item 1 should still be shown')
        self.is_(self.menu_item('item2'), None, 'menu item 2 should still be hidden')

        self.close_menu()
        head.open_action_context_menu(self, extension, 'browser')
        extension.await_message('onShown fired')

        # Now after closing and re-opening the menu, the latest contextual info
        # should be used.
        self.is_(self.menu_item('item1'), None, 'menu item 1 should be hidden')
        self.expect_label('item2', 'menu item 2 should be shown')

        self.close_menu()
        extension.unload()
        self.browser.close_target(tab)
