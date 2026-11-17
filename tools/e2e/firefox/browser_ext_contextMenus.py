"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus.js.

Firefox's top-level menu of an add-on ("top-level-menu") is, in this
browser, the item with the add-on's name, here Firefox's default name. A
check before a click on the item it counts ends the test when the item is
missing, as Firefox's click on a missing item does. SpecialPowers.spawn()'s
selections run in the page.

The bookmark tasks take this browser's places for Firefox's: the bookmark
bar for the bookmarks toolbar (its context menu is the browser's own), the
bookmarks side panel for the bookmarks sidebar, and the bookmark manager's
page (chrome://bookmarks) at the bookmark bar's folder for the Library. The
side panel's and the manager's context menus are their pages' own (a
cr-action-menu), so the port right-clicks with DevTools' input there and
reads the menu's buttons. Firefox's PlacesUtils is the bookmarks API on the
bookmark manager's page. Left out: test_legacy_bookmark_sidebar_contextmenu,
which runs the sidebar task again on Firefox's old bookmarks sidebar (the
pref sidebar.updatedBookmarks.enabled off); this browser has one bookmarks
side panel.
"""

import json

from firefox import head
from extension_test_utils import JS
from harness import wait_for

PAGE = f'{head.BASE}context.html'

# The first element, in the page or in a shadow root, for which the
# function `pred` (JavaScript's source) holds: a WebUI page's elements are in
# its components' shadow roots.
FIND = '''(pred => {
  const find = root => {
    for (const el of root.querySelectorAll("*")) {
      if (pred(el)) {
        return el;
      }
      const found = el.shadowRoot && find(el.shadowRoot);
      if (found) {
        return found;
      }
    }
    return null;
  };
  return find(document);
})'''


def find(pred):
    """JavaScript for the element that FIND finds with `pred`."""
    return f'{FIND}({pred})'


# The bookmarks side panel's row of the bookmark bar's folder.
TOOLBAR_FOLDER_ROW = find('el => el.id == "bookmark-SIDE_PANEL_BOOKMARK_BAR_ID"')

# The WebUI menu that is open: a cr-action-menu, whose items are its buttons.
OPEN_MENU = find('el => el.tagName == "CR-ACTION-MENU" && el.open')


def click_in(page, element, button='left'):
    """A mouse click at the centre of `element` (JavaScript for it) in a
    WebUI page, as DevTools' input: Firefox's synthesizeMouseAtCenter().
    The click waits until the element stops moving: a side panel folder's
    rows slide into place."""
    last = {}

    def settled():
        rect = page.eval(f'(() => {{ const r = ({element}).getBoundingClientRect();'
                         ' return [r.x + r.width / 2, r.y + r.height / 2, r.width]; })()')
        previous, last['rect'] = last.get('rect'), rect
        return rect[2] and rect == previous and rect
    x, y, _ = wait_for(settled, interval=0.1, what='the element to stop moving')
    for kind in ('mouseMoved', 'mousePressed', 'mouseReleased'):
        page.call('Input.dispatchMouseEvent', type=kind, x=x, y=y, button=button, clickCount=1)


def webui_menu_labels(page):
    """The labels of the open WebUI menu's shown items, or None."""
    return page.eval(f'(() => {{ const menu = {OPEN_MENU};'
                     ' return menu && [...menu.querySelectorAll("button")]'
                     '.filter(b => !b.hidden && b.getClientRects().length)'
                     '.map(b => b.textContent.trim()); })()')


def open_webui_context_menu(page, element):
    """openChromeContextMenu() on a WebUI page: a right click on `element`;
    the labels of the menu's items, once it is open."""
    click_in(page, element, button='right')
    return wait_for(lambda: webui_menu_labels(page), what="the page's context menu to open")


def close_webui_context_menu(page, label=None):
    """closeChromeContextMenu() on a WebUI page: a click on the open menu's
    item labelled `label`, or no item to close the menu; either way the menu
    closes."""
    if label is None:
        page.eval(f'{OPEN_MENU}.close()')
    else:
        click_in(page, f'[...{OPEN_MENU}.querySelectorAll("button")]'
                       f'.find(b => b.textContent.trim() == {json.dumps(label)})')
    wait_for(lambda: page.eval(f'!{OPEN_MENU}'), what="the page's context menu to close")


def bookmark_context_menu_extension(test):
    return test.load_extension(
        manifest={
            'permissions': ['contextMenus', 'bookmarks', 'activeTab'],
        },
        background=JS('''async function background() {
          const url = "https://example.com/";
          const title = "Example";
          let newBookmark = await browser.bookmarks.create({
            url,
            title,
            parentId: "toolbar_____",
          });
          browser.contextMenus.onClicked.addListener(async (info, tab) => {
            browser.test.assertEq(
              undefined,
              tab,
              "click event in bookmarks menu is not associated with any tab"
            );
            browser.test.assertEq(
              newBookmark.id,
              info.bookmarkId,
              "Bookmark ID matches"
            );

            await browser.test.assertRejects(
              browser.tabs.executeScript({ code: "'some code';" }),
              /Missing host permission for the tab/,
              "Content script should not run, activeTab should not be granted to bookmark menu events"
            );

            let [bookmark] = await browser.bookmarks.get(info.bookmarkId);
            browser.test.assertEq(title, bookmark.title, "Bookmark title matches");
            browser.test.assertEq(url, bookmark.url, "Bookmark url matches");
            browser.test.assertFalse(
              info.hasOwnProperty("pageUrl"),
              "Context menu does not expose pageUrl"
            );
            await browser.bookmarks.remove(info.bookmarkId);
            browser.test.sendMessage("test-finish");
          });
          browser.contextMenus.create(
            {
              title: "Get bookmark",
              contexts: ["bookmark"],
            },
            () => {
              browser.test.sendMessage("bookmark-created", newBookmark.id);
            }
          );
        }'''))


def bookmark_folder_context_menu_extension(test):
    return test.load_extension(
        manifest={
            'permissions': ['contextMenus', 'bookmarks'],
        },
        background=JS('''async function background() {
          const title = "Example";
          let newBookmark = await browser.bookmarks.create({
            title,
            parentId: "toolbar_____",
          });
          await new Promise(resolve =>
            browser.contextMenus.create(
              {
                title: "Get bookmark",
                contexts: ["bookmark"],
              },
              resolve
            )
          );
          browser.contextMenus.onClicked.addListener(async info => {
            browser.test.assertEq(
              newBookmark.id,
              info.bookmarkId,
              "Bookmark ID matches"
            );

            let [bookmark] = await browser.bookmarks.get(info.bookmarkId);
            browser.test.assertEq(title, bookmark.title, "Bookmark title matches");
            browser.test.assertFalse(
              info.hasOwnProperty("pageUrl"),
              "Context menu does not expose pageUrl"
            );
            await browser.bookmarks.remove(info.bookmarkId);
            browser.test.sendMessage("test-finish");
          });
          browser.test.sendMessage("bookmark-created", newBookmark.id);
        }'''))


class ContextMenusTest(head.ContextMenuTest):

    def test_01(self):
        tab1 = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function () {
              browser.test.assertEq(
                browser.contextMenus.ContextType.TAB,
                "tab",
                "ContextType is available"
              );
              browser.contextMenus.create({
                id: "clickme-image",
                title: "Click me!",
                contexts: ["image"],
              });
              browser.contextMenus.create(
                {
                  id: "clickme-page",
                  title: "Click me!",
                  contexts: ["page"],
                },
                () => {
                  browser.test.sendMessage("ready");
                }
              );
            }'''))

        extension.startup()
        extension.await_message('ready')

        content_area_context_menu = head.open_context_menu(self, tab1, '#img1')
        item = content_area_context_menu.by_label('Click me!')
        self.is_(len(item), 1, 'contextMenu item for image was found')
        head.close_context_menu(self)

        content_area_context_menu = head.open_context_menu(self, tab1, 'body')
        item = content_area_context_menu.by_label('Click me!')
        self.is_(len(item), 1, 'contextMenu item for page was found')
        head.close_context_menu(self)

        extension.unload()

        self.browser.close_target(tab1)

    def test_02(self):
        tab1 = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''async function () {
              browser.test.onMessage.addListener(msg => {
                if (msg == "removeall") {
                  browser.contextMenus.removeAll();
                  browser.test.sendMessage("removed");
                }
              });

              // A generic onclick callback function.
              function genericOnClick(info, tab) {
                browser.test.sendMessage("onclick", { info, tab });
              }

              browser.contextMenus.onClicked.addListener((info, tab) => {
                browser.test.sendMessage("browser.contextMenus.onClicked", {
                  info,
                  tab,
                });
              });

              browser.contextMenus.create({
                contexts: ["all"],
                type: "separator",
              });

              let contexts = [
                "page",
                "link",
                "selection",
                "image",
                "editable",
                "password",
              ];
              for (let i = 0; i < contexts.length; i++) {
                let context = contexts[i];
                let title = context;
                browser.contextMenus.create({
                  title: title,
                  contexts: [context],
                  id: "ext-" + context,
                  onclick: genericOnClick,
                });
                if (context == "selection") {
                  browser.contextMenus.update("ext-selection", {
                    title: "selection is: '%s'",
                    onclick: genericOnClick,
                  });
                }
              }

              let parent = browser.contextMenus.create({
                title: "parent",
              });
              browser.contextMenus.create({
                title: "child1",
                parentId: parent,
                onclick: genericOnClick,
              });
              let child2 = browser.contextMenus.create({
                title: "child2",
                parentId: parent,
                onclick: genericOnClick,
              });

              let parentToDel = browser.contextMenus.create({
                title: "parentToDel",
              });
              browser.contextMenus.create({
                title: "child1",
                parentId: parentToDel,
                onclick: genericOnClick,
              });
              browser.contextMenus.create({
                title: "child2",
                parentId: parentToDel,
                onclick: genericOnClick,
              });
              browser.contextMenus.remove(parentToDel);

              browser.contextMenus.create({
                title: "Without onclick property",
                id: "ext-without-onclick",
              });

              await browser.test.assertRejects(
                browser.contextMenus.update(parent, { parentId: child2 }),
                /cannot be an ancestor/,
                "Should not be able to reparent an item as descendent of itself"
              );

              browser.test.sendMessage("contextmenus");
            }'''))

        extension.startup()
        extension.await_message('contextmenus')

        expected_click_info = {
            'menuItemId': 'ext-image',
            'mediaType': 'image',
            'srcUrl': f'{head.BASE}ctxmenu-image.png',
            'pageUrl': PAGE,
            'editable': False,
        }

        def check_click_info(result):
            for i in expected_click_info:
                self.is_(result['info'].get(i), expected_click_info[i],
                         f'click info {i} expected to be: {expected_click_info[i]} '
                         f"but was: {result['info'].get(i)}")
            self.is_(expected_click_info.get('pageSrc'), (result.get('tab') or {}).get('url'),
                     'click info page source is the right tab')

        def await_clicks(with_onclick=True):
            if with_onclick:
                check_click_info(extension.await_message('onclick'))
            result = extension.await_message('browser.contextMenus.onClicked')
            check_click_info(result)
            return result

        def one(items, message):
            """is(items.length, 1, message) for an item that is clicked next."""
            self.assertEqual(len(items), 1, message)
            return items[0]

        extension_menu_root = head.open_extension_context_menu(self, tab1)
        self.assertIsNotNone(extension_menu_root, "the add-on's menu")

        # Check some menu items
        image = one(extension_menu_root.by_label('image'),
                    'contextMenu item for image was found (context=image)')

        items = extension_menu_root.by_label('selection-edited')
        self.is_(len(items), 0, 'contextMenu item for selection was not found (context=image)')

        items = extension_menu_root.by_label('parentToDel')
        self.is_(len(items), 0,
                 'contextMenu item for removed parent was not found (context=image)')

        items = extension_menu_root.by_label('parent')
        self.is_(len(items), 1, 'contextMenu item for parent was found (context=image)')

        if items:
            children = head.open_submenu(self, items[0]).items
            self.is_(len(children), 2, 'child items for parent were found (context=image)')

        # Click on ext-image item and check the click results
        head.close_extension_context_menu(self, image)

        await_clicks()

        # Test "link" context and OnClick data property.
        extension_menu_root = head.open_extension_context_menu(self, tab1, '[href=some-link]')

        # Click on ext-link and check the click results
        link = one(extension_menu_root.by_label('link'),
                   'contextMenu item for parent was found (context=link)')

        expected_click_info = {
            'menuItemId': 'ext-link',
            'linkUrl': f'{head.BASE}some-link',
            'linkText': 'Some link',
            'pageUrl': PAGE,
            'editable': False,
        }

        head.close_extension_context_menu(self, link)

        await_clicks()

        # Test "editable" context and OnClick data property.
        extension_menu_root = head.open_extension_context_menu(self, tab1, '#edit-me')

        # Check some menu items.
        editable = one(extension_menu_root.by_label('editable'),
                       'contextMenu item for text input element was found (context=editable)')

        # Click on ext-editable item and check the click results.
        head.close_extension_context_menu(self, editable)

        expected_click_info = {
            'menuItemId': 'ext-editable',
            'pageUrl': PAGE,
            'editable': True,
        }

        await_clicks()

        extension_menu_root = head.open_extension_context_menu(self, tab1, '#readonly-text')

        # Check some menu items.
        items = extension_menu_root.by_label('editable')
        self.is_(len(items), 0, 'contextMenu item for text input element was not found '
                 '(context=editable fails for readonly items)')

        # Hide the popup "manually" because there's nothing to click.
        head.close_context_menu(self)

        # Test "editable" context on type=tel and type=number items, and OnClick data property.
        extension_menu_root = head.open_extension_context_menu(self, tab1, '#call-me-maybe')

        # Check some menu items.
        editable = one(extension_menu_root.by_label('editable'),
                       'contextMenu item for text input element was found (context=editable)')

        # Click on ext-editable item and check the click results.
        head.close_extension_context_menu(self, editable)

        expected_click_info = {
            'menuItemId': 'ext-editable',
            'pageUrl': PAGE,
            'editable': True,
        }

        await_clicks()

        extension_menu_root = head.open_extension_context_menu(self, tab1, '#number-input')

        # Check some menu items.
        editable = one(extension_menu_root.by_label('editable'),
                       'contextMenu item for text input element was found (context=editable)')

        # Click on ext-editable item and check the click results.
        head.close_extension_context_menu(self, editable)

        expected_click_info = {
            'menuItemId': 'ext-editable',
            'pageUrl': PAGE,
            'editable': True,
        }

        await_clicks()

        extension_menu_root = head.open_extension_context_menu(self, tab1, '#password')
        password = one(extension_menu_root.by_label('password'),
                       'contextMenu item for password input element was found (context=password)')
        head.close_extension_context_menu(self, password)
        expected_click_info = {
            'menuItemId': 'ext-password',
            'pageUrl': PAGE,
            'editable': True,
        }

        await_clicks()

        extension_menu_root = head.open_extension_context_menu(self, tab1, '#noneditablepassword')
        password = one(extension_menu_root.by_label('password'),
                       'contextMenu item for password input element was found (context=password)')
        head.close_extension_context_menu(self, password)
        expected_click_info['editable'] = False
        await_clicks()

        # Select some text
        tab1.eval('''(() => {
          let doc = document;
          let range = doc.createRange();
          let selection = window.getSelection();
          selection.removeAllRanges();
          let textNode = doc.getElementById("img1").previousSibling;
          range.setStart(textNode, 0);
          range.setEnd(textNode, 100);
          selection.addRange(range);
        })()''')

        # Bring up context menu again
        extension_menu_root = head.open_extension_context_menu(self, tab1)

        # Check some menu items
        item = one(extension_menu_root.by_label('Without onclick property'),
                   'contextMenu item was found (context=page)')

        head.close_extension_context_menu(self, item)

        expected_click_info = {
            'menuItemId': 'ext-without-onclick',
            'pageUrl': PAGE,
        }

        await_clicks(with_onclick=False)

        # Bring up context menu again
        extension_menu_root = head.open_extension_context_menu(self, tab1)

        # Check some menu items
        selection_item = one(
            extension_menu_root.by_label(
                "selection is: 'just some text 12345678901234567890123456789012…'"),
            'contextMenu item for selection was found (context=selection)')

        items = extension_menu_root.by_label('selection')
        self.is_(len(items), 0, 'contextMenu item label update worked (context=selection)')

        head.close_extension_context_menu(self, selection_item)

        expected_click_info = {
            'menuItemId': 'ext-selection',
            'pageUrl': PAGE,
            'selectionText': ' just some text 12345678901234567890123456789012345678901234567890'
                             '12345678901234567890123456789012',
        }

        await_clicks()

        # Select a lot of text
        tab1.eval('''(() => {
          let doc = document;
          let range = doc.createRange();
          let selection = window.getSelection();
          selection.removeAllRanges();
          let textNode = doc.getElementById("longtext").firstChild;
          range.setStart(textNode, 0);
          range.setEnd(textNode, textNode.length);
          selection.addRange(range);
        })()''')

        # Bring up context menu again
        extension_menu_root = head.open_extension_context_menu(self, tab1, '#longtext')

        # Check some menu items
        item = one(
            extension_menu_root.by_label(
                "selection is: 'Sed ut perspiciatis unde omnis iste natus error…'"),
            'contextMenu item for longtext selection was found (context=selection)')
        head.close_extension_context_menu(self, item)

        expected_click_info = {
            'menuItemId': 'ext-selection',
            'pageUrl': PAGE,
        }

        result = await_clicks()
        self.assertTrue((result['info'].get('selectionText') or '')
                        .endswith('quo voluptas nulla pariatur?'),
                        'long text selection worked')

        # Select a lot of text, excercise the editable element code path in
        # the Browser:GetSelection handler.
        tab1.eval('''(() => {
          let doc = document;
          let node = doc.getElementById("editabletext");
          // content.js handleContentContextMenu fails intermittently without focus.
          node.focus();
          node.selectionStart = 0;
          node.selectionEnd = 844;
        })()''')

        # Bring up context menu again
        extension_menu_root = head.open_extension_context_menu(self, tab1, '#editabletext')

        # Check some menu items
        item = one(extension_menu_root.by_label('editable'),
                   'contextMenu item for text input element was found (context=editable)')
        head.close_extension_context_menu(self, item)

        expected_click_info = {
            'menuItemId': 'ext-editable',
            'editable': True,
            'pageUrl': PAGE,
        }

        result = await_clicks()
        self.assertTrue((result['info'].get('selectionText') or '')
                        .endswith('perferendis doloribus asperiores repellat.'),
                        'long text selection worked')

        extension.send_message('removeall')
        extension.await_message('removed')

        content_area_context_menu = head.open_context_menu(self, tab1, '#img1')
        items = content_area_context_menu.by_label('Generated extension')
        self.is_(len(items), 0, 'top level item was not found (after removeAll()')
        head.close_context_menu(self)

        extension.unload()
        self.browser.close_target(tab1)

    def test_remove_all_with_two_extensions(self):
        tab = self.open_tab(PAGE)
        manifest = {'permissions': ['contextMenus']}

        first = self.load_extension(
            manifest=manifest,
            background=JS('''function background() {
              browser.contextMenus.create({ title: "alpha", contexts: ["all"] });

              browser.contextMenus.onClicked.addListener(() => {
                browser.contextMenus.removeAll();
              });
              browser.test.onMessage.addListener(msg => {
                if (msg == "ping") {
                  browser.test.sendMessage("pong-alpha");
                  return;
                }
                browser.contextMenus.create({ title: "gamma", contexts: ["all"] });
              });
            }'''))

        second = self.load_extension(
            manifest=manifest,
            background=JS('''function background() {
              browser.contextMenus.create({ title: "beta", contexts: ["all"] });

              browser.contextMenus.onClicked.addListener(() => {
                browser.contextMenus.removeAll();
              });

              browser.test.onMessage.addListener(() => {
                browser.test.sendMessage("pong-beta");
              });
            }'''))

        first.startup()
        second.startup()

        def confirm_menu_items(*items):
            # Round-trip to extension to make sure that the context menu state has been
            # updated by the async contextMenus.create / contextMenus.removeAll calls.
            first.send_message('ping')
            second.send_message('ping')
            first.await_message('pong-alpha')
            second.await_message('pong-beta')

            menu = head.open_context_menu(self, tab, '#img1')
            for item_id in ['alpha', 'beta', 'gamma']:
                expected = item_id in items
                found = menu.by_label(item_id)
                self.is_(bool(found), expected,
                         f'menu item {item_id} {"" if expected else "not "}found')
            # Return the first menu item, we need to click it.
            found = menu.by_label(items[0])
            self.assertTrue(found, f'menu item {items[0]} found')
            return found[0]

        # Confirm alpha, beta exist; click alpha to remove it.
        alpha = confirm_menu_items('alpha', 'beta')
        head.close_extension_context_menu(self, alpha)

        # Confirm only beta exists.
        confirm_menu_items('beta')
        head.close_context_menu(self)

        # Create gamma, confirm, click.
        first.send_message('create')
        beta = confirm_menu_items('beta', 'gamma')
        head.close_extension_context_menu(self, beta)

        # Confirm only gamma is left.
        confirm_menu_items('gamma')
        head.close_context_menu(self)

        first.unload()
        second.unload()
        self.browser.close_target(tab)

    def bookmarks_call(self, call):
        """A bookmarks API call (JavaScript, `chrome.bookmarks.<call>`) on the
        bookmark manager's page, which stands for Firefox's PlacesUtils."""
        page = self.open_tab('chrome://bookmarks')
        try:
            return page.eval(f'chrome.bookmarks.{call}')
        finally:
            self.browser.close_target(page)

    def last_bookmark_button(self):
        """#PersonalToolbar .bookmark-item:last-child: the bookmark bar's last
        bookmark."""
        def last():
            buttons = [v for v in self.browser.views('BookmarkButton') if v.visible]
            return max(buttons, key=lambda v: v.bounds['x']) if buttons else None
        return self.browser.wait_settled(last, what="the bookmark bar's last bookmark")

    def test_bookmark_contextmenu(self):
        # Adding a bookmark to the bookmarks toolbar.
        added_bookmark = self.bookmarks_call(
            'create({parentId: "1", title: "Test", url: "https://example.com"}).then(b => b.id)')
        self.addCleanup(self.bookmarks_call, f'remove({json.dumps(added_bookmark)})')

        tab = self.open_tab(PAGE)

        head.toggle_bookmarks_toolbar(self, True)

        extension = bookmark_context_menu_extension(self)

        extension.startup()
        extension.await_message('bookmark-created')
        menu = head.open_chrome_context_menu(self, self.last_bookmark_button())

        menu_item = menu.by_label('Get bookmark')
        self.assertEqual(len(menu_item), 1, "the menu has the add-on's item")
        head.close_extension_context_menu(self, menu_item[0])

        extension.await_message('test-finish')
        extension.unload()
        head.toggle_bookmarks_toolbar(self, False)

        self.browser.close_target(tab)

    def show_bookmarks_side_panel(self):
        """SidebarTestUtils.bookmarks.showBookmarksSidebar(): the bookmarks
        side panel, from the app menu; its page."""
        self.browser.click_view(self.browser.wait_view('BrowserAppMenuButton'))
        menus = head.open_menus(self)
        app_menu = head.Menu(self, [item for group in menus[0] for item in group])
        bookmarks = head.open_submenu(self, app_menu.by_label('Bookmarks')[0])
        self.browser.click_view(bookmarks.by_label('Show bookmarks in side panel')[0])
        page = self.browser.page('chrome://bookmarks-side-panel.top-chrome/')
        wait_for(lambda: page.eval(f'!!{TOOLBAR_FOLDER_ROW}'),
                 what='the side panel to list the bookmark bar')
        return page

    def close_side_panel(self):
        """SidebarTestUtils.closePanel(): the side panel's close button."""
        def button():
            return next((v for v in self.browser.views('ImageButton')
                         if v.visible and v['TooltipText'] == 'Close side panel'), None)
        self.browser.click_view(self.browser.wait_settled(button, what="the side panel's close button"))
        wait_for(lambda: not any(v.visible for v in self.browser.views('SidePanel')),
                 what='the side panel to close')

    def test_bookmark_sidebar_contextmenu(self):
        tab = self.open_tab(PAGE)

        extension = bookmark_context_menu_extension(self)
        extension.startup()
        bookmark_guid = extension.await_message('bookmark-created')

        side_panel = self.show_bookmarks_side_panel()
        # openToolbarFolder()
        side_panel.eval(f'{TOOLBAR_FOLDER_ROW}.shadowRoot.querySelector("power-bookmark-row-item")'
                        '.shadowRoot.querySelector("cr-url-list-item").click()')
        row = find(f'el => el.id == {json.dumps("bookmark-" + bookmark_guid)}')
        wait_for(lambda: side_panel.eval(f'!!{row}'), what="the bookmark's row")

        labels = open_webui_context_menu(side_panel, row)

        self.assertIn('Get bookmark', labels, "the menu has the add-on's item")
        close_webui_context_menu(side_panel, 'Get bookmark')
        self.close_side_panel()
        extension.await_message('test-finish')
        extension.unload()

        self.browser.close_target(tab)

    def test_organizer_contextmenu(self):
        tab = self.open_tab(PAGE)
        # promiseLibrary("BookmarksToolbar"): the bookmark manager at the
        # bookmark bar.
        library = self.open_tab('chrome://bookmarks/?id=1')

        main_tree = 'BOOKMARKS-ITEM'
        left_tree = 'BOOKMARKS-FOLDER-NODE'
        tests = [
            [main_tree, bookmark_context_menu_extension],
            [main_tree, bookmark_folder_context_menu_extension],
            [left_tree, bookmark_folder_context_menu_extension],
        ]

        for tree, make_extension in tests:
            extension = make_extension(self)
            extension.startup()
            bookmark_guid = extension.await_message('bookmark-created')

            # The manager's items have the bookmarks' UUIDs, and their
            # API IDs as `legacyId`.
            node = find(f'el => el.tagName == "{main_tree}" && el.item_'
                        f' && String(el.item_.legacyId) == {json.dumps(bookmark_guid)}')
            wait_for(lambda: library.eval(f'!!{node}'), what='the bookmark in the bookmark manager')
            if tree == left_tree:
                # tree.selectItems([bookmarkGuid]): in the left tree, selecting
                # the folder opens it, as a click on it does.
                uuid = library.eval(f'{node}.itemId')
                library.call('Page.navigate', url=f'chrome://bookmarks/?id={uuid}')
                node = find(f'el => el.tagName == "{left_tree}" && el.itemId == {json.dumps(uuid)}')
                # The folder's own row, not its children's.
                node = f'{node}?.shadowRoot.querySelector("#container")'
            wait_for(lambda: library.eval(f'!!{node}'), what='the bookmark in the bookmark manager')
            labels = open_webui_context_menu(library, node)

            self.assertIn('Get bookmark', labels, "the menu has the add-on's item")
            close_webui_context_menu(library, 'Get bookmark')
            extension.await_message('test-finish')
            extension.unload()

        self.browser.close_target(library)
        self.browser.close_target(tab)

    def test_bookmark_context_requires_permission(self):
        # In Firefox, this task right-clicks the bookmark that
        # test_bookmark_contextmenu added, which stays until the file ends
        # (registerCleanupFunction()). Tests here run in any order, so this
        # one adds it too.
        added_bookmark = self.bookmarks_call(
            'create({parentId: "1", title: "Test", url: "https://example.com"}).then(b => b.id)')
        self.addCleanup(self.bookmarks_call, f'remove({json.dumps(added_bookmark)})')

        head.toggle_bookmarks_toolbar(self, True)

        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
            },
            background=JS('''function background() {
              browser.contextMenus.create(
                {
                  title: "Get bookmark",
                  contexts: ["bookmark"],
                },
                () => {
                  browser.test.sendMessage("bookmark-created");
                }
              );
            }'''))
        extension.startup()
        extension.await_message('bookmark-created')
        menu = head.open_chrome_context_menu(self, self.last_bookmark_button())

        self.is_(len(menu.by_label('Get bookmark')), 0,
                 'bookmark context menu not created with `bookmarks` permission.')

        head.close_context_menu(self)

        extension.unload()
        head.toggle_bookmarks_toolbar(self, False)
