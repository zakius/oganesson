"""Port of Firefox's
browser/components/extensions/test/xpcshell/test_ext_menu_startup.js.

The add-ons' code is Firefox's, as it is. Firefox reads the add-on's menus
from Gecko's map of them (ExtensionMenus.getMenus()); here they are the
browser's own menus, as the add-on's user sees them: the page's context menu
on head.py's context.html and the tab's context menu, each item with its
children in its submenu (expect_extension_menus()). An item's contexts are
which of the two menus shows it.

Firefox's restart of the add-on manager is a restart of the browser
(restart_browser()), which loads the add-on again from --load-extension:
Chromium takes that for an update, so the add-on's runtime.onInstalled runs
again, and its event page starts with the browser, where Firefox's waits for
an event. After a restart the port awaits what those send, then stops the
page. Firefox's extension.upgrade() is upgrade(): the add-on's folder gets the
new manifest, and chrome://extensions reloads it. terminateBackground() waits
for Chromium's own idle time, as MenusEventPageIdReuseTest's does: a shorter
one would stop the page before a slow run's message reaches it. For the
same reason the tasks whose add-on only answers messages wake its page
before each one (send()), which Firefox's 30 s idle time doesn't need.

Left out: everything that reads Gecko's menus store on disk
(expectExtensionMenus()'s checkSaved, _hasStoredExtensionData(), the
webext-persisted-menus-updated notification), the MenuItem objects that
webext-menus-created hands over (the menus themselves show their nesting), and
the extensions.webextensions.menus.writeDebounceTime pref; and the tasks that
only test Gecko's store: test_ExtensionMenus_after_extension_hasShutdown,
test_corrupted_menus_store_data and test_unnecessary_kvstore_dir_not_created.
"""

import json

from firefox import head
from extension_test_utils import JS
from harness import wait_for

NAME = 'Generated extension'
PAGE = f'{head.BASE}context.html'
# The titles of all the tasks' items: an add-on's one item in a menu is
# found by its title.
TITLES = {'top-level', 'parent', 'click A', 'click B', 'click updated', 'some-menu',
          'first', 'second', 'third', 'fourth', 'menu title'}


def get_extension(gecko_id, background, version='1.0'):
    return {
        'manifest': {
            'version': version,
            'browser_specific_settings': {'gecko': {'id': gecko_id}},
            'permissions': ['menus'],
            'background': {'persistent': False},
        },
        'background': background,
    }


EXT_PAGE_SCRIPT = JS('''function extPageScriptWithMenusCreateAndUpdateTestHandler() {
  browser.test.onMessage.addListener((msg, ...args) => {
    switch (msg) {
      case "menusCreate": {
        const menuDetails = args[0];
        browser.menus.create(menuDetails, () => {
          browser.test.assertEq(
            undefined,
            browser.runtime.lastError?.message,
            "Expect the menu to be created successfully"
          );
          browser.test.sendMessage(`${msg}:done`);
        });
        break;
      }
      case "menusUpdate": {
        const menuId = args[0];
        const menuDetails = args[1];
        browser.test.log(`Updating "${menuId}: ${JSON.stringify(menuDetails)}`);
        browser.menus.update(menuId, menuDetails, () => {
          browser.test.assertEq(
            undefined,
            browser.runtime.lastError?.message,
            "Expect the menu to be created successfully"
          );
          browser.test.sendMessage(`${msg}:done`);
        });
        break;
      }
      default:
        browser.test.fail(`Got unexpected test message: ${msg}`);
        browser.test.sendMessage(`${msg}:done`);
    }
  });
  browser.test.sendMessage("extpage:ready");
}''')

NESTED_BACKGROUND = JS('''async function background() {
  browser.test.onMessage.addListener(async (action, properties) => {
    browser.test.log(`onMessage ${action}`);
    switch (action) {
      case "create":
        await new Promise(resolve => {
          browser.menus.create(properties, resolve);
        });
        break;
      case "update":
        {
          let { id, ...update } = properties;
          await browser.menus.update(id, update);
        }
        break;
      case "remove":
        {
          let { id } = properties;
          await browser.menus.remove(id);
        }
        break;
      case "removeAll":
        await browser.menus.removeAll();
        break;
    }
    browser.test.sendMessage("updated");
  });
}''')


def expected_tree(menus, contexts):
    """The items of Firefox's menus map `menus` (their create properties, in
    the map's order) that a menu of `contexts` shows, as [[title, children]].
    An item without contexts has its parent's, or else "all"."""
    def own_contexts(props):
        if 'contexts' in props:
            return props['contexts']
        parent = next((p for p in menus if p['id'] == props.get('parentId')), None)
        return own_contexts(parent) if parent else ['all']

    def children(parent_id):
        return [[props['title'], children(props['id'])] for props in menus
                if props.get('parentId') == parent_id
                and set(own_contexts(props)) & set(contexts)]
    return children(None)


class MenuStartupTest(head.ContextMenuTest):

    def load(self, details):
        return self.load_extension(use_addon_manager='permanent', **details)

    def background_running(self, extension):
        prefix = f'chrome-extension://{extension.id}/'
        return any(target['url'].startswith(prefix) and target['type'] == 'background_page'
                   for target in self.browser.targets())

    def send(self, extension, *args):
        """extension.sendMessage() to an event page that may have gone idle
        since its last message: it wakes first."""
        extension.wakeup_background()
        extension.send_message(*args)

    def read_items(self, items):
        """[[title, children]] of `items`, those of the last open menu, each
        submenu opened, read and closed in turn."""
        tree = []
        for item in items:
            children = []
            if head.has_submenu(self, item):
                depth = len(self.browser.menus())
                children = self.read_items(head.open_submenu(self, item).items)

                def closed():
                    # An Escape while the submenu still opens is lost: again.
                    if len(self.browser.menus()) <= depth:
                        return True
                    self.browser.key('Escape')
                    return False
                wait_for(closed, interval=0.5, what='the submenu to close')
            tree.append([head.label_of(item), children])
        return tree

    def shown_tree(self, menu, titles):
        """The add-on's items in the open `menu`: those of its submenu, or
        else its one item, whose title is one of `titles`."""
        group = menu.by_label(NAME)
        if group:
            return self.read_items(head.open_submenu(self, group[0]).items)
        return self.read_items([item for item in menu.items if head.label_of(item) in titles])

    def expect_extension_menus(self, expect):
        """expectExtensionMenus(): the page's and the tab's context menus show
        the items of Firefox's menus map `expect`, nested and in order."""
        page = self.open_tab(PAGE)
        try:
            menu = head.open_context_menu(self, page, '#longtext')
            self.is_(json.dumps(self.shown_tree(menu, TITLES)),
                     json.dumps(expected_tree(expect, ['all', 'page'])),
                     "expected properties exist in the menus map (the page's menu)")
            head.close_context_menu(self)
            menu = head.open_tab_context_menu(self)
            self.is_(json.dumps(self.shown_tree(menu, TITLES)),
                     json.dumps(expected_tree(expect, ['tab'])),
                     "expected properties exist in the menus map (the tab's menu)")
            head.close_context_menu(self)
        finally:
            self.browser.close_target(page)

    def upgrade(self, extension, details):
        """extension.upgrade(): the add-on's folder gets the version of the
        add-on `details`, the same add-on otherwise, and chrome://extensions
        reloads it; its background starts again."""
        extension.manifest['version'] = details['manifest']['version']
        (extension.folder / 'manifest.json').write_text(json.dumps(extension.manifest))
        extension.ready = False
        page = self.open_tab('chrome://extensions')
        try:
            wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
            page.eval(f'chrome.developerPrivate.reload({json.dumps(extension.id)}, '
                      '{failQuietly: true})')
        finally:
            self.browser.close_target(page)
        self.wait_reports(lambda: extension.ready, 'the upgraded background to load')

    def test_01_menu_onInstalled(self):
        background = JS('''async function background() {
          browser.runtime.onInstalled.addListener(async () => {
            const parentId = browser.menus.create({
              contexts: ["all"],
              title: "parent",
              id: "test-parent",
            });
            browser.menus.create({
              parentId,
              title: "click A",
              id: "test-click-a",
            });
            browser.menus.create(
              {
                parentId,
                title: "click B",
                id: "test-click-b",
              },
              () => {
                browser.test.sendMessage("onInstalled");
              }
            );
          });
          browser.menus.create(
            {
              contexts: ["tab"],
              title: "top-level",
              id: "test-top-level",
            },
            () => {
              browser.test.sendMessage("create", browser.runtime.lastError?.message);
            }
          );

          browser.test.onMessage.addListener(async msg => {
            browser.test.log(`onMessage ${msg}`);
            if (msg == "updatemenu") {
              await browser.menus.update("test-click-a", { title: "click updated" });
            } else if (msg == "removemenu") {
              await browser.menus.remove("test-click-b");
            } else if (msg == "removeall") {
              await browser.menus.removeAll();
            }
            browser.test.sendMessage("updated");
          });
        }''')
        extension = self.load(get_extension('test-persist@mochitest', background))

        extension.startup()
        last_error = extension.await_message('create')
        self.is_(last_error, None, 'no error creating menu')
        extension.await_message('onInstalled')
        extension.terminate_background()

        self.expect_extension_menus([
            {'contexts': ['tab'], 'id': 'test-top-level', 'title': 'top-level'},
            {'contexts': ['all'], 'id': 'test-parent', 'title': 'parent'},
            {'id': 'test-click-a', 'parentId': 'test-parent', 'title': 'click A'},
            {'id': 'test-click-b', 'parentId': 'test-parent', 'title': 'click B'},
        ])

        extension.wakeup_background()
        last_error = extension.await_message('create')
        self.is_(last_error, 'The menu id test-top-level already exists in menus.create.',
                 'correct error creating menu')

        self.restart_browser()
        # The page starts with the browser, and onInstalled runs again: the
        # restored items are there before either creates its own.
        last_error = extension.await_message('create')
        self.is_(last_error, 'The menu id test-top-level already exists in menus.create.',
                 'correct error creating menu')
        extension.await_message('onInstalled')
        extension.terminate_background()

        # After the extension or the AddonManager has been shutdown,
        # we expect the menu store task to have written the menus
        # on disk and so we expect these menus to be loaded back
        # in memory and also stored on disk.
        self.expect_extension_menus([
            {'contexts': ['tab'], 'id': 'test-top-level', 'title': 'top-level'},
            {'contexts': ['all'], 'id': 'test-parent', 'title': 'parent'},
            {'id': 'test-click-a', 'parentId': 'test-parent', 'title': 'click A'},
            {'id': 'test-click-b', 'parentId': 'test-parent', 'title': 'click B'},
        ])

        self.check(not self.background_running(extension), 'background is not running')
        extension.wakeup_background()
        last_error = extension.await_message('create')
        self.is_(last_error, 'The menu id test-top-level already exists in menus.create.',
                 'correct error creating menu')

        extension.send_message('updatemenu')
        extension.await_message('updated')
        extension.terminate_background()

        # Title change is persisted.
        self.expect_extension_menus([
            {'contexts': ['tab'], 'id': 'test-top-level', 'title': 'top-level'},
            {'contexts': ['all'], 'id': 'test-parent', 'title': 'parent'},
            {'id': 'test-click-a', 'parentId': 'test-parent', 'title': 'click updated'},
            {'id': 'test-click-b', 'parentId': 'test-parent', 'title': 'click B'},
        ])

        extension.wakeup_background()
        last_error = extension.await_message('create')
        self.is_(last_error, 'The menu id test-top-level already exists in menus.create.',
                 'correct error creating menu')

        extension.send_message('removemenu')
        extension.await_message('updated')
        extension.terminate_background()

        # menu removed
        self.expect_extension_menus([
            {'contexts': ['tab'], 'id': 'test-top-level', 'title': 'top-level'},
            {'contexts': ['all'], 'id': 'test-parent', 'title': 'parent'},
            {'id': 'test-click-a', 'parentId': 'test-parent', 'title': 'click updated'},
        ])

        extension.wakeup_background()
        last_error = extension.await_message('create')
        self.is_(last_error, 'The menu id test-top-level already exists in menus.create.',
                 'correct error creating menu')

        extension.send_message('removeall')
        extension.await_message('updated')
        extension.terminate_background()

        # menus removed
        self.expect_extension_menus([])

        extension.unload()

    def test_02_menu_persisted_cleared_after_ext_update(self):
        background = JS('''async function background() {
          browser.test.onMessage.addListener(async (action, properties) => {
            browser.test.log(`onMessage ${action}`);
            switch (action) {
              case "create":
                await new Promise(resolve => {
                  browser.menus.create(properties, resolve);
                });
                break;
              default:
                browser.test.fail(`Got unexpected test message "${action}"`);
                break;
            }
            browser.test.sendMessage("updated");
          });
        }''')

        extension = self.load(get_extension('test-nesting@mochitest', background, '1.0'))
        extension.startup()

        self.send(extension, 'create',
                  {'id': 'stored-menu', 'contexts': ['all'], 'title': 'some-menu'})
        extension.await_message('updated')

        expected_menus = [{'contexts': ['all'], 'id': 'stored-menu', 'title': 'some-menu'}]
        self.expect_extension_menus(expected_menus)

        # Re-install the same add-on version and expect persisted menus to
        # still exist.
        self.upgrade(extension, get_extension('test-nesting@mochitest', background, '1.0'))
        self.expect_extension_menus(expected_menus)

        # Upgrade to a new add-on version and expect persisted menus to be
        # cleared.
        self.upgrade(extension, get_extension('test-nesting@mochitest', background, '2.0'))
        self.expect_extension_menus([])

        extension.unload()

    def test_03_menu_nested(self):
        extension = self.load(get_extension('test-nesting@mochitest', NESTED_BACKGROUND))
        extension.startup()

        self.send(extension, 'create', {'id': 'first', 'contexts': ['all'], 'title': 'first'})
        extension.await_message('updated')
        self.expect_extension_menus([
            {'contexts': ['all'], 'id': 'first', 'title': 'first'},
        ])

        self.send(extension, 'create', {'id': 'second', 'contexts': ['all'], 'title': 'second'})
        extension.await_message('updated')
        self.expect_extension_menus([
            {'contexts': ['all'], 'id': 'first', 'title': 'first'},
            {'contexts': ['all'], 'id': 'second', 'title': 'second'},
        ])

        self.send(extension, 'create', {
            'id': 'third',
            'contexts': ['all'],
            'title': 'third',
            'parentId': 'first',
        })
        extension.await_message('updated')
        self.expect_extension_menus([
            {'contexts': ['all'], 'id': 'first', 'title': 'first'},
            {'contexts': ['all'], 'id': 'second', 'title': 'second'},
            {'contexts': ['all'], 'id': 'third', 'parentId': 'first', 'title': 'third'},
        ])

        self.send(extension, 'create', {'id': 'fourth', 'contexts': ['all'], 'title': 'fourth'})
        extension.await_message('updated')
        self.expect_extension_menus([
            {'contexts': ['all'], 'id': 'first', 'title': 'first'},
            {'contexts': ['all'], 'id': 'second', 'title': 'second'},
            {'contexts': ['all'], 'id': 'third', 'parentId': 'first', 'title': 'third'},
            {'contexts': ['all'], 'id': 'fourth', 'title': 'fourth'},
        ])

        self.send(extension, 'update', {'id': 'first', 'parentId': 'second'})
        extension.await_message('updated')
        self.expect_extension_menus([
            {'contexts': ['all'], 'id': 'second', 'title': 'second'},
            {'contexts': ['all'], 'id': 'fourth', 'title': 'fourth'},
            {'contexts': ['all'], 'id': 'first', 'title': 'first', 'parentId': 'second'},
            {'contexts': ['all'], 'id': 'third', 'parentId': 'first', 'title': 'third'},
        ])

        self.restart_browser()
        extension.wakeup_background()

        self.expect_extension_menus([
            {'contexts': ['all'], 'id': 'second', 'title': 'second'},
            {'contexts': ['all'], 'id': 'fourth', 'title': 'fourth'},
            {'contexts': ['all'], 'id': 'first', 'title': 'first', 'parentId': 'second'},
            {'contexts': ['all'], 'id': 'third', 'parentId': 'first', 'title': 'third'},
        ])

        self.send(extension, 'remove', {'id': 'second'})
        extension.await_message('updated')
        self.expect_extension_menus([
            {'contexts': ['all'], 'id': 'fourth', 'title': 'fourth'},
        ])

        self.send(extension, 'removeAll')
        extension.await_message('updated')
        self.expect_extension_menus([])

        extension.unload()

    def test_04_extension_without_background(self):
        # This test ensures that menus created by an extension without a
        # background page are not persisted.
        extension = self.load({
            'manifest': {
                'permissions': ['menus'],
            },
            'files': {
                'extpage.html': '<!DOCTYPE html><script src="extpage.js"></script>',
                'extpage.js': EXT_PAGE_SCRIPT,
            },
        })

        def test_create_menu():
            page = self.open_tab(f'chrome-extension://{extension.id}/extpage.html')
            extension.await_message('extpage:ready')
            menu_details = {'id': 'test-menu', 'title': 'menu title'}
            extension.send_message('menusCreate', menu_details)
            extension.await_message('menusCreate:done')
            self.browser.close_target(page)

        extension.startup()
        test_create_menu()

        # Simulated browser restart and verify no menu was persisted or
        # restored.
        self.restart_browser()
        # Try to create the same menu again, if it does fail the menu was
        # unexpectectly restored.
        test_create_menu()
        extension.unload()
