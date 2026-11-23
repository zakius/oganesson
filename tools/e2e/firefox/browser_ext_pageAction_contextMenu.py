"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_contextMenu.js.

The add-on's code is Firefox's, as it is. clickPageAction() is a real click
on the page action's button in the location bar (head.click_page_action()),
which opens the add-on's popup (open_page_action_popup());
openContextMenuInPopup() is a right click in the popup, as
head.open_context_menu_in_sidebar() makes one.

pageaction_popup_contextmenu_hidden_items: Firefox finds the context menu's
items by their IDs, Gecko's DOM; here they are the items of this browser's
menu with the same use, by label (ITEMS). Firefox's context-navigation is
the Back, Forward and Reload items, context-viewsource View page source,
and context-inspect Inspect. This browser's menu has no item to inspect
accessibility properties (context-inspect-a11y) nor to bookmark the page
(context-bookmarkpage): those are hidden. A separator isn't an item here:
context-sep-navigation shows when a navigation item ends a group of items,
and inspect-separator when Inspect starts one that isn't the first. The
test runs on Linux: the macOS items are left out. Firefox's pref
ui.mouse.right_click.select_under_cursor is left out: a right click selects
the word under it only on macOS.

pageaction_popup_image_contextmenu: context-copyimage is Copy image.
"""

from extension_test_utils import JS
from firefox import head
from harness import Page, wait_for

EXT_DATA = {
    'manifest': {
        'permissions': ['contextMenus'],
        'page_action': {
            'default_popup': 'popup.html',
        },
    },
    'use_addon_manager': 'temporary',

    'files': {
        'popup.html': '''
      <!DOCTYPE html>
      <html>
      <head><meta charset="utf-8"/>
      </head>
      <body>
      <span id="text">A Test Popup</span>
      <img id="testimg" src="data:image/svg+xml,<svg></svg>" height="10" width="10">
      </body></html>
    ''',
    },

    'background': JS('''function () {
    browser.contextMenus.create(
      {
        id: "clickme-page",
        title: "Click me!",
        contexts: ["all"],
      },
      () => browser.test.sendMessage("menus-created")
    );
    browser.tabs.query({ active: true, currentWindow: true }, tabs => {
      const tabId = tabs[0].id;

      browser.pageAction.show(tabId).then(() => {
        browser.test.sendMessage("action-shown");
      });
    });
  }'''),
}

# Firefox's contextMenuItems on Linux, by item ID: "hidden", or "" for shown
# and enabled.
CONTEXT_MENU_ITEMS = {
    'context-sep-navigation': 'hidden',
    'context-viewsource': '',
    'inspect-separator': 'hidden',
    'context-inspect': 'hidden',
    'context-inspect-a11y': 'hidden',
    'context-bookmarkpage': 'hidden',
    'context-navigation': 'hidden',
}

# The labels of this browser's items for Firefox's item IDs.
ITEMS = {
    'context-navigation': ('Back', 'Forward', 'Reload'),
    'context-viewsource': ('View page source',),
    'context-inspect': ('Inspect',),
    'context-inspect-a11y': (),
    'context-bookmarkpage': (),
}


def items_by_id(menu, item_id):
    """querySelector(`#${itemID}`): the menu's items for Firefox's item ID,
    shown; for a separator, the item next to it."""
    if item_id == 'context-sep-navigation':
        return [item for item in items_by_id(menu, 'context-navigation') if menu.ends_group(item)]
    if item_id == 'inspect-separator':
        return [item for item in items_by_id(menu, 'context-inspect')
                if any(group[0] is item for group in menu.groups[1:])]
    return [item for label in ITEMS[item_id] for item in menu.by_label(label)]


def open_page_action_popup(test, extension):
    """clickPageAction() and awaitExtensionPanel(): a click on the add-on's
    page action button; its popup, once loaded."""
    prefix = f'chrome-extension://{extension.id}/popup.html'
    before = {target['id'] for target in test.browser.targets()}
    head.click_page_action(test, extension)
    target = wait_for(lambda: next((t for t in test.browser.targets()
                                    if t['id'] not in before and t['url'].startswith(prefix)),
                                   None),
                      what="the page action's popup")
    popup = Page(target)
    wait_for(lambda: popup.eval('document.readyState') == 'complete', what='the popup to load')
    return popup


class PageActionContextMenuTest(head.ContextMenuTest):

    def start(self):
        extension = self.load_extension(**EXT_DATA)
        extension.startup()
        extension.await_message('menus-created')
        extension.await_message('action-shown')
        return extension

    def test_01_pageaction_popup_contextmenu(self):
        extension = self.start()

        popup = open_page_action_popup(self, extension)
        content_area_context_menu = head.open_context_menu_in_sidebar(self, popup)
        item = content_area_context_menu.by_label('Click me!')
        self.is_(len(item), 1, 'contextMenu item for page was found')
        head.close_context_menu(self)
        popup.close()

        extension.unload()

    def test_02_pageaction_popup_contextmenu_hidden_items(self):
        extension = self.start()

        popup = open_page_action_popup(self, extension)
        head.open_context_menu_in_sidebar(self, popup, '#text')
        # The menu again, with its groups of items between separators.
        content_area_context_menu = head.first_menu(self)

        for item_id, state in CONTEXT_MENU_ITEMS.items():
            items = items_by_id(content_area_context_menu, item_id)
            if state == 'hidden':
                self.check(not items, f'{item_id} is {state}')
            else:
                self.check(bool(items), f'{item_id} is not hidden')
                self.check(all(item['Enabled'] == 'true' for item in items),
                           f'{item_id} is not disabled')

        head.close_context_menu(self)
        popup.close()

        extension.unload()

    def test_03_pageaction_popup_image_contextmenu(self):
        extension = self.start()

        popup = open_page_action_popup(self, extension)
        content_area_context_menu = head.open_context_menu_in_sidebar(self, popup, '#testimg')

        item = content_area_context_menu.by_label('Copy image')
        self.check(bool(item), 'context-copyimage is not hidden')
        self.check(bool(item) and item[0]['Enabled'] == 'true', 'context-copyimage is not disabled')

        head.close_context_menu(self)
        popup.close()

        extension.unload()
