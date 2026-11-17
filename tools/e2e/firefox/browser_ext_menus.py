"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus.js.

Firefox's menus are DOM trees; here a menu is the items it shows, in groups
between separators (head.py). An item's `tagName` "menu" is an item that
opens a submenu (head.has_submenu()). Firefox's item IDs
(`<widget id>-menuitem-_<id>`) are Gecko's DOM, so the port checks which
item it is by its label, as each item's label names its ID. A separator is
the end of a group of items (head.Menu). Each kind of action menu is a
subtest, so that the toolbar button's menu is checked while the page action
has no button (zakius/oganesson#68). A check before a click on the item it
reads ends the test when the item is missing, or isn't the one Firefox's
test clicks, as Firefox's click on a missing item does. Left out, as
Gecko's DOM: that the submenu opened is the item's own menupopup, and the
overflow submenu's `ext-type` attribute; the submenu's label is checked.

In the tab menu and the app menu's More tools, this browser puts the
add-ons' items in a group of their own among its own items, where Firefox
puts them last, after a separator: the port takes that group for Firefox's
last three children, and its first item for the one after the separator.

The bookmark task takes the bookmark bar for Firefox's bookmarks toolbar, as
the contextMenus port does. Firefox's Tools menu is, in this browser, the app
menu's More tools (head.open_tools_menu()). `http://example.com/` is the test
server, as mochitest's proxy makes it in Firefox.
"""

import json

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'
EXAMPLE = 'http://example.com/'
ROUTES = {**head.ROUTES, '/': (200, {'Content-Type': 'text/html'}, b'<!DOCTYPE html>')}


class MenusTest(head.ContextMenuTest):
    hosts = ('mochi.test', 'example.com')
    routes = ROUTES

    def test_01_permissions(self):
        background = JS('''function background() {
          browser.test.sendMessage("apis", {
            menus: typeof browser.menus,
            contextMenus: typeof browser.contextMenus,
            menusInternal: typeof browser.menusInternal,
          });
        }''')

        first = self.load_extension(manifest={'permissions': ['menus']}, background=background)
        second = self.load_extension(manifest={'permissions': ['contextMenus']},
                                     background=background)

        first.startup()
        second.startup()

        apis1 = first.await_message('apis')
        apis2 = second.await_message('apis')

        self.is_(apis1['menus'], 'object', "browser.menus available with 'menus' permission")
        self.is_(apis1['contextMenus'], 'undefined',
                 "browser.contextMenus unavailable with  'menus' permission")
        self.is_(apis1['menusInternal'], 'undefined', 'browser.menusInternal is never available')

        self.is_(apis2['menus'], 'undefined',
                 "browser.menus unavailable with 'contextMenus' permission")
        self.is_(apis2['contextMenus'], 'object',
                 "browser.contextMenus unavailable with  'contextMenus' permission")
        self.is_(apis2['menusInternal'], 'undefined', 'browser.menusInternal is never available')

        first.unload()
        second.unload()

    def test_02_action_context_menus(self):
        manifest = {
            'page_action': {},
            'browser_action': {
                'default_area': 'navbar',
            },
            'permissions': ['menus'],
        }

        background = JS('''async function background() {
          const contexts = ["page_action", "browser_action"];

          const parentId = browser.menus.create({ contexts, title: "parent" });
          browser.menus.create({ parentId, title: "click A" });
          browser.menus.create({ parentId, title: "click B" });

          for (let i = 1; i < 9; i++) {
            browser.menus.create({ contexts, id: `${i}`, title: `click ${i}` });
          }

          browser.menus.onClicked.addListener((info, tab) => {
            browser.test.sendMessage("click", { info, tab });
          });

          const [tab] = await browser.tabs.query({ active: true });
          await browser.pageAction.show(tab.id);
          browser.test.sendMessage("ready", tab.id);
        }''')

        extension = self.load_extension(manifest=manifest, background=background)
        tab = self.open_tab(EXAMPLE)

        extension.startup()
        tab_id = extension.await_message('ready')

        for kind in ('page', 'browser'):
            with self.subTest(kind=kind):
                menu = head.open_action_context_menu(self, extension, kind)
                submenu, second, last = menu.items[0], menu.items[1], menu.items[5]

                self.is_(head.has_submenu(self, submenu), True, 'Correct submenu type')
                self.is_(head.label_of(submenu), 'parent', 'Correct submenu title')

                self.assertEqual(head.label_of(submenu), 'parent', 'the first item is parent')
                self.assertTrue(head.has_submenu(self, submenu), 'parent opens a submenu')
                popup = head.open_submenu(self, submenu)
                self.is_(len(popup.items), 2, 'Correct number of submenu items')

                self.is_(head.has_submenu(self, second), False, 'Second menu item type is correct')
                self.is_(head.label_of(second), 'click 1', 'Second menu item title is correct')

                self.is_(head.has_submenu(self, last), True, 'Last menu item type is correct')
                self.is_(head.label_of(last), 'Generated extension', 'Last menu item title is correct')
                self.is_(menu.ends_group(last), True, 'Separator after last menu item')

                # Verify that menu items exceeding ACTION_MENU_TOP_LEVEL_LIMIT are moved into a submenu.
                head.close_context_menu(self)
                menu = head.open_action_context_menu(self, extension, kind)
                last = menu.items[5]
                self.assertTrue(head.has_submenu(self, last), 'the sixth item opens a submenu')
                overflow_popup = head.open_submenu(self, last)
                self.is_(len(overflow_popup.items), 4, 'Excess items should be moved into a submenu')
                self.is_(head.label_of(overflow_popup.items[0]), 'click 5',
                         'First submenu item ID is correct')
                self.is_(head.label_of(overflow_popup.items[-1]), 'click 8',
                         'Last submenu item ID is correct')

                head.close_extension_context_menu(self, overflow_popup.items[0])
                click = extension.await_message('click')
                self.is_(click['info']['pageUrl'], EXAMPLE, 'Click info pageUrl is correct')
                self.is_(click['tab']['id'], tab_id, 'Click event tab ID is correct')

        self.browser.close_target(tab)
        extension.unload()

    def bookmarks_call(self, call):
        """A bookmarks API call (JavaScript, `chrome.bookmarks.<call>`) on the
        bookmark manager's page, which stands for Firefox's PlacesUtils."""
        page = self.open_tab('chrome://bookmarks')
        try:
            return page.eval(f'chrome.bookmarks.{call}')
        finally:
            self.browser.close_target(page)

    def last_bookmark_button(self):
        """The bookmark bar's last bookmark: Firefox's
        #PlacesToolbarItems .bookmark-item finds the only one."""
        def last():
            buttons = [v for v in self.browser.views('BookmarkButton') if v.visible]
            return max(buttons, key=lambda v: v.bounds['x']) if buttons else None
        return self.browser.wait_settled(last, what="the bookmark bar's last bookmark")

    def test_03_bookmark_context_menu(self):
        # Adding a bookmark to the bookmarks toolbar.
        added_bookmark = self.bookmarks_call(
            'create({parentId: "1", title: "Test", url: "https://example.com"}).then(b => b.id)')
        self.addCleanup(self.bookmarks_call, f'remove({json.dumps(added_bookmark)})')

        ext = self.load_extension(
            manifest={
                'permissions': ['menus', 'bookmarks'],
            },
            background=JS('''function background() {
              browser.menus.onShown.addListener(() => {
                browser.test.sendMessage("hello");
              });
              browser.menus.create({ title: "blarg", contexts: ["bookmark"] }, () => {
                browser.test.sendMessage("ready");
              });
            }'''))

        ext.startup()
        ext.await_message('ready')
        head.toggle_bookmarks_toolbar(self, True)

        menu = head.open_chrome_context_menu(self, self.last_bookmark_button())
        item = menu.items[-1]
        self.is_(head.label_of(item), 'blarg', 'Menu item label is correct')
        ext.await_message('hello')  # onShown listener fired

        self.assertEqual(head.label_of(item), 'blarg', "the last item is the add-on's")
        head.close_extension_context_menu(self, item)
        ext.unload()
        head.toggle_bookmarks_toolbar(self, False)

    def test_04_tab_context_menu(self):
        first = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              browser.menus.create({
                id: "alpha-beta-parent",
                title: "alpha-beta parent",
                contexts: ["tab"],
              });

              browser.menus.create({ parentId: "alpha-beta-parent", title: "alpha" });
              browser.menus.create({ parentId: "alpha-beta-parent", title: "beta" });

              browser.menus.create({ title: "dummy", contexts: ["page"] });

              browser.menus.onClicked.addListener((info, tab) => {
                browser.test.sendMessage("click", { info, tab });
              });

              const [tab] = await browser.tabs.query({ active: true });
              browser.test.sendMessage("ready", tab.id);
            }'''))

        second = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''function background() {
              browser.menus.create({
                title: "invisible",
                contexts: ["tab"],
                documentUrlPatterns: ["http://does/not/match"],
              });
              browser.menus.create(
                {
                  title: "gamma",
                  contexts: ["tab"],
                  documentUrlPatterns: ["http://example.com/"],
                },
                () => {
                  browser.test.sendMessage("ready");
                }
              );
            }'''))

        tab = self.open_tab(EXAMPLE)
        first.startup()
        second.startup()

        tab_id = first.await_message('ready')
        second.await_message('ready')

        menu = head.open_tab_context_menu(self)
        # The add-ons' items: Firefox's last three children, a separator,
        # the submenu and gamma, are a group of their own here.
        group = next((g for g in menu.groups
                      if any(head.label_of(item) == 'alpha-beta parent' for item in g)), [])
        self.assertEqual(len(group), 2, "the menu has the add-ons' two items")
        submenu, gamma = group
        self.is_(head.label_of(submenu), 'alpha-beta parent', 'Correct submenu title')
        self.is_(head.has_submenu(self, submenu), True, 'Correct submenu type')

        self.check(head.label_of(gamma) != 'dummy',
                   '`page` context menu item should not appear here')

        self.is_(head.has_submenu(self, gamma), False, 'Third menu item type is correct')
        self.is_(head.label_of(gamma), 'gamma', 'Third menu item label is correct')

        popup = head.open_submenu(self, submenu)
        self.is_(len(popup.items), 2, 'Correct number of submenu items')
        self.assertEqual(len(popup.items), 2, 'the submenu has alpha and beta')

        alpha, beta = popup.items
        self.is_(head.has_submenu(self, alpha), False, 'First menu item type is correct')
        self.is_(head.label_of(alpha), 'alpha', 'First menu item label is correct')
        self.is_(head.has_submenu(self, beta), False, 'Second menu item type is correct')
        self.is_(head.label_of(beta), 'beta', 'Second menu item label is correct')

        head.close_extension_context_menu(self, beta)
        click = first.await_message('click')
        self.is_(click['info']['pageUrl'], EXAMPLE, 'Click info pageUrl is correct')
        self.is_(click['tab']['id'], tab_id, 'Click event tab ID is correct')
        self.is_(click['info'].get('frameId'), None, 'no frameId on chrome')

        self.browser.close_target(tab)
        first.unload()
        second.unload()

    def test_05_onclick_frameid(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''function background() {
              function onclick(info) {
                browser.test.sendMessage("click", info);
              }
              browser.menus.create(
                { contexts: ["frame", "page"], title: "modify", onclick },
                () => {
                  browser.test.sendMessage("ready");
                }
              );
            }'''))
        tab = self.open_tab(PAGE)

        extension.startup()
        extension.await_message('ready')

        def click(menu):
            items = menu.by_label('modify')
            self.is_(len(items), 1, 'found menu item')
            self.assertTrue(items, 'the menu has the item')
            head.close_extension_context_menu(self, items[0])
            return extension.await_message('click')

        info = click(head.open_context_menu(self, tab, 'body'))
        self.is_(info.get('frameId'), 0, 'top level click')
        info = click(head.open_context_menu(self, tab, 'body', frame_index=0))
        self.check(info.get('frameId') is not None, 'frame click, frameId is not undefined')
        self.check(info.get('frameId') != 0, 'frame click, frameId probably okay')

        self.browser.close_target(tab)
        extension.unload()

    def test_06_multiple_contexts_init(self):
        tab = self.open_tab(PAGE)
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''function background() {
              browser.menus.create({ id: "parent", title: "parent" }, () => {
                browser.tabs.create({ url: "tab.html", active: false });
              });
            }'''),
            files={
                'tab.html': '<!DOCTYPE html><meta charset=utf-8><script src=tab.js></script>',
                'tab.js': JS('''function () {
                  browser.menus.onClicked.addListener(info => {
                    browser.test.sendMessage("click", info);
                  });
                  browser.menus.create(
                    { parentId: "parent", id: "child", title: "child" },
                    () => {
                      browser.test.sendMessage("ready");
                    }
                  );
                }'''),
            })

        extension.startup()
        extension.await_message('ready')

        menu = head.open_context_menu(self, tab)
        items = menu.by_label('parent')

        self.is_(len(items), 1, 'Found parent menu item')
        self.assertTrue(items, 'the menu has the parent item')
        self.is_(head.has_submenu(self, items[0]), True, 'And it has children')

        popup = head.open_submenu(self, items[0])
        self.is_(head.label_of(popup.items[0]), 'child', 'Correct child menu item')
        head.close_extension_context_menu(self, popup.items[0])

        info = extension.await_message('click')
        self.is_(info['menuItemId'], 'child', 'onClicked the correct item')

        self.browser.close_target(tab)
        extension.unload()

    def test_07_tools_menu(self):
        first = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''function background() {
              browser.menus.create({ title: "alpha", contexts: ["tools_menu"] });
              browser.menus.create({ title: "beta", contexts: ["tools_menu"] }, () => {
                browser.test.sendMessage("ready");
              });
            }'''))

        second = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              browser.menus.create({ title: "gamma", contexts: ["tools_menu"] });
              browser.menus.onClicked.addListener((info, tab) => {
                browser.test.sendMessage("click", { info, tab });
              });

              const [tab] = await browser.tabs.query({ active: true });
              browser.test.sendMessage("ready", tab.id);
            }'''))

        tab = self.open_tab(EXAMPLE)
        first.startup()
        second.startup()

        first.await_message('ready')
        tab_id = second.await_message('ready')
        menu = head.open_tools_menu(self)

        # Firefox's last three children, a separator, the submenu and gamma:
        # the add-ons' items are a group of their own here.
        group = next((g for g in menu.groups
                      if any(head.label_of(item) == 'gamma' for item in g)), [])
        self.assertEqual(len(group), 2, "the menu has the add-ons' two items")
        submenu, gamma = group

        self.is_(head.has_submenu(self, submenu), True, 'Correct submenu type')
        self.is_(head.label_of(submenu), 'Generated extension', 'Correct submenu title')
        self.is_(len(head.open_submenu(self, submenu).items), 2, 'Correct number of submenu items')

        self.is_(head.has_submenu(self, gamma), False, 'Third menu item type is correct')
        self.is_(head.label_of(gamma), 'gamma', 'Third menu item label is correct')

        head.close_extension_context_menu(self, gamma)

        click = second.await_message('click')
        self.is_(click['info']['pageUrl'], EXAMPLE, 'Click info pageUrl is correct')
        self.is_(click['tab']['id'], tab_id, 'Click event tab ID is correct')

        self.browser.close_target(tab)
        first.unload()
        second.unload()
