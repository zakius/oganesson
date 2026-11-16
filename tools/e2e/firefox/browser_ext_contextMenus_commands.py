"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_commands.js.

Firefox's menu label is the item's title; the add-on's submenu is under its
name, "contextMenus commands"."""

from firefox import head
from extension_test_utils import JS, FirefoxTest

TEST_HTML = '<!DOCTYPE html><meta charset="utf-8"><script src="test.js"></script>'
PAGE = f'{head.BASE}context.html?test=commands'


class ContextMenusCommandsTest(FirefoxTest):
    hosts = ('mochi.test',)
    routes = head.ROUTES

    def test_actions_context_menu(self):
        background = JS('''function background() {
            browser.contextMenus.create({
              title: "open_browser_action",
              contexts: ["all"],
              command: "_execute_browser_action",
            });
            browser.contextMenus.create({
              title: "open_page_action",
              contexts: ["all"],
              command: "_execute_page_action",
            });
            browser.contextMenus.create({
              title: "open_sidebar_action",
              contexts: ["all"],
              command: "_execute_sidebar_action",
            });
            browser.tabs.onUpdated.addListener(tabId => {
              browser.pageAction.show(tabId);
            });
            browser.contextMenus.onClicked.addListener(() => {
              browser.test.fail(`menu onClicked should not have been received`);
            });
            browser.test.sendMessage("ready");
          }''')

        test_script = JS('''function testScript() {
            browser.test.log(`testScript executing on ${window.location.href}\\n`);
            window.onload = () => {
              browser.test.sendMessage("test-opened", true);
            };
          }''')

        extension = self.load_extension(
            manifest={
                'name': 'contextMenus commands',
                'permissions': ['contextMenus', 'activeTab', 'tabs'],
                'browser_action': {
                    'default_title': 'Test BrowserAction',
                    'default_popup': 'test.html?type=browserAction',
                    'browser_style': True,
                },
                'page_action': {
                    'default_title': 'Test PageAction',
                    'default_popup': 'test.html?type=pageAction',
                    'browser_style': True,
                },
                'sidebar_action': {
                    'default_title': 'Test Sidebar',
                    'default_panel': 'test.html?type=sidebarAction',
                    'open_at_install': False,
                },
            },
            background=background,
            files={
                'test.html': TEST_HTML,
                'test.js': test_script,
            })

        def test_context(id):
            menu = head.open_extension_context_menu(self, tab, name='contextMenus commands')
            items = menu.by_label(id)
            self.assertEqual(len(items), 1, 'exactly one menu item found')
            head.close_extension_context_menu(self, items[0])
            return extension.await_message('test-opened')

        extension.startup()
        extension.await_message('ready')

        # open a page so page action works
        tab = self.open_tab(PAGE)

        self.assertTrue(test_context('open_sidebar_action'), '_execute_sidebar_action worked')
        self.assertTrue(test_context('open_browser_action'), '_execute_browser_action worked')
        self.assertTrue(test_context('open_page_action'), '_execute_page_action worked')

        self.browser.close_target(tab)
        extension.unload()

    def test_v3_action_context_menu(self):
        extension = self.load_extension(
            manifest={
                'name': 'contextMenus commands',
                'manifest_version': 3,
                'permissions': ['contextMenus'],
                'action': {
                    'default_title': 'Test Action',
                    'default_popup': 'test.html',
                    'browser_style': True,
                },
            },
            background=JS('''function background() {
              browser.contextMenus.onClicked.addListener(() => {
                browser.test.fail(`menu onClicked should not have been received`);
              });

              browser.contextMenus.create(
                {
                  id: "open_action",
                  title: "open_action",
                  contexts: ["all"],
                  command: "_execute_action",
                },
                () => {
                  browser.test.sendMessage("ready");
                }
              );
            }'''),
            files={
                'test.html': TEST_HTML,
                'test.js': JS('''() => {
                  window.onload = () => {
                    browser.test.sendMessage("test-opened", true);
                  };
                }'''),
            })

        def test_context(id):
            menu = head.open_context_menu(self, tab)
            items = menu.by_label(id)
            self.assertEqual(len(items), 1, 'exactly one menu item found')
            head.close_extension_context_menu(self, items[0])
            return extension.await_message('test-opened')

        extension.startup()
        extension.await_message('ready')

        tab = self.open_tab(PAGE)

        self.assertTrue(test_context('open_action'), '_execute_action worked')

        self.browser.close_target(tab)
        extension.unload()
