"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_eventpage.js.

Firefox's pref extensions.eventPages.enabled is on by default here: Manifest
V2 event pages always run. terminateBackground() is quick with
EVENT_PAGE_ARGS (MenusEventPageIdReuseTest says why its task goes without).
SimpleTest.monitorConsole() forbids Firefox's report of an unchecked
`lastError`; the port forbids this browser's ("Unchecked runtime.lastError")
in the browser's log while the task runs. Firefox's check that the
background is "stopped" after the popup opened (Gecko's
`backgroundState`) is the port's check that the add-on has no running
background page. As in the menus port, the action menu's first item is
taken for Firefox's first child (#156 for the order), and a check before the
click on it ends the test when it isn't the item Firefox clicks. Firefox's
window shows about:blank, which the menu tasks' `pageUrl` names: the port
opens a tab at about:blank, as the harness's first tab is the new tab page.
"""

from firefox import head
from extension_test_utils import EVENT_PAGE_ARGS, JS

PAGE = f'{head.BASE}context.html?test=commands'


class EventPageTest(head.ContextMenuTest):
    """The tasks' helpers."""

    def get_extension(self, background, use_addon_manager=None):
        return self.load_extension(
            use_addon_manager=use_addon_manager,
            manifest={
                'browser_action': {
                    'default_area': 'navbar',
                },
                'permissions': ['menus'],
                'background': {'persistent': False},
            },
            background=background)

    def log_size(self):
        with open(self.browser.log_path, 'rb') as log:
            return len(log.read())

    def forbid_unchecked_last_error(self, since):
        """SimpleTest.endMonitorConsole() with the forbidden message: the
        browser's log since `since` (log_size()) has no unchecked
        lastError."""
        with open(self.browser.log_path, 'rb') as log:
            log.seek(since)
            lines = log.read().decode(errors='replace').splitlines()
        found = [line for line in lines if 'Unchecked runtime.lastError' in line]
        self.check(not found, f'no unchecked lastError is logged - Actual: {found}')

    def background_running(self, extension):
        prefix = f'chrome-extension://{extension.id}/'
        return any(target['url'].startswith(prefix) and target['type'] == 'background_page'
                   for target in self.browser.targets())



class MenusEventPageTest(EventPageTest):
    browser_args = (*EventPageTest.browser_args, *EVENT_PAGE_ARGS)

    def test_01_menu_create_id(self):
        since = self.log_size()

        extension = self.get_extension(JS('''function background() {
          // Event pages require ID
          browser.menus.create(
            { contexts: ["browser_action"], title: "parent" },
            () => {
              browser.test.assertEq(
                "menus.create requires an id for non-persistent background scripts.",
                browser.runtime.lastError?.message,
                "lastError message for missing id"
              );
              browser.test.sendMessage("done");
            }
          );
        }'''))
        extension.startup()
        extension.await_message('done')
        extension.unload()

        self.forbid_unchecked_last_error(since)

    def test_02_menu_onclick(self):
        extension = self.get_extension(JS('''async function background() {
          const contexts = ["browser_action"];

          const parentId = browser.menus.create({
            contexts,
            title: "parent",
            id: "test-parent",
          });
          browser.menus.create({ parentId, title: "click A", id: "test-click" });

          browser.menus.onClicked.addListener((info, tab) => {
            browser.test.sendMessage("click", { info, tab });
          });
          browser.runtime.onSuspend.addListener(() => {
            browser.test.sendMessage("suspended-test_menu_onclick");
          });
        }'''))

        blank = self.open_tab('about:blank')
        self.addCleanup(self.browser.close_target, blank)
        extension.startup()
        extension.terminate_background()  # Simulated suspend on idle.
        extension.await_message('suspended-test_menu_onclick')

        # The background is now suspended, test that a menu click starts it.
        kind = 'browser'

        menu = head.open_action_context_menu(self, extension, kind)
        submenu = menu.items[0]
        self.assertEqual(head.label_of(submenu), 'parent', 'the first item is parent')
        popup = head.open_submenu(self, submenu)

        head.close_extension_context_menu(self, popup.items[0])
        clicked = extension.await_message('click')
        self.is_(clicked['info'].get('pageUrl'), 'about:blank', 'Click info pageUrl is correct')
        self.check(clicked['tab']['id'] > -1, 'Click event tab ID is correct')

        extension.unload()

    def test_03_menu_onshown(self):
        extension = self.get_extension(JS('''async function background() {
          const contexts = ["browser_action"];

          const parentId = browser.menus.create({
            contexts,
            title: "parent",
            id: "test-parent",
          });
          browser.menus.create({ parentId, title: "click A", id: "test-click" });

          browser.menus.onClicked.addListener((info, tab) => {
            browser.test.sendMessage("click", { info, tab });
          });
          browser.menus.onShown.addListener((info, tab) => {
            browser.test.sendMessage("shown", { info, tab });
          });
          browser.menus.onHidden.addListener((info, tab) => {
            browser.test.sendMessage("hidden", { info, tab });
          });
          browser.runtime.onSuspend.addListener(() => {
            browser.test.sendMessage("suspended-test_menu_onshown");
          });
        }'''))

        blank = self.open_tab('about:blank')
        self.addCleanup(self.browser.close_target, blank)
        extension.startup()
        extension.terminate_background()  # Simulated suspend on idle.
        extension.await_message('suspended-test_menu_onshown')

        # The background is now suspended, test that showing a menu starts it.
        kind = 'browser'

        menu = head.open_action_context_menu(self, extension, kind)
        submenu = menu.items[0]
        self.assertEqual(head.label_of(submenu), 'parent', 'the first item is parent')
        popup = head.open_submenu(self, submenu)
        extension.await_message('shown')

        head.close_extension_context_menu(self, popup.items[0])
        extension.await_message('hidden')
        # The click still should work after the background was restarted.
        clicked = extension.await_message('click')
        self.is_(clicked['info'].get('pageUrl'), 'about:blank', 'Click info pageUrl is correct')
        self.check(clicked['tab']['id'] > -1, 'Click event tab ID is correct')

        extension.unload()

    def test_04_actions_context_menu(self):
        extension = self.load_extension(
            manifest={
                'name': 'contextMenus commands',
                'permissions': ['contextMenus'],
                'browser_action': {
                    'default_title': 'Test BrowserAction',
                    'default_popup': 'test.html',
                    'default_area': 'navbar',
                    'browser_style': True,
                },
                'background': {'persistent': False},
            },
            background=JS('''function background() {
              browser.contextMenus.create({
                id: "my_browser_action",
                title: "open_browser_action",
                contexts: ["all"],
                command: "_execute_browser_action",
              });
              browser.contextMenus.onClicked.addListener(() => {
                browser.test.fail(`menu onClicked should not have been received`);
              });
              browser.test.sendMessage("ready");
            }'''),
            files={
                'test.html': '<!DOCTYPE html><meta charset="utf-8"><script src="test.js"></script>',
                'test.js': JS('''function testScript() {
                  window.onload = () => {
                    browser.test.sendMessage("test-opened", true);
                  };
                }'''),
            })

        def test_context(label, page):
            menu = head.open_context_menu(self, page)
            items = menu.by_label(label)
            self.is_(len(items), 1, 'exactly one menu item found')
            self.assertTrue(items, f'the menu has the item {label!r}')
            head.close_extension_context_menu(self, items[0])
            return extension.await_message('test-opened')

        extension.startup()
        extension.await_message('ready')
        extension.terminate_background()

        # open a page so context menu works
        tab = self.open_tab(PAGE)

        self.check(test_context('open_browser_action', tab), '_execute_browser_action worked')

        self.browser.close_target(tab)
        self.check(not self.background_running(extension), 'background is not running')

        extension.unload()



class MenusEventPageIdReuseTest(EventPageTest):
    """The last task, in a browser of its own: its add-on's event page has
    to stay up until the task stops it, as Firefox's does, and
    EVENT_PAGE_ARGS stops an idle one after a second, before a slow run's
    message reaches it. Chromium's own idle time (10 s, and 5 s to suspend)
    is shorter than terminate_background()'s wait."""

    def test_05_menu_create_id_reuse(self):
        since = self.log_size()

        extension = self.get_extension(JS('''function background() {
          browser.menus.create(
            {
              contexts: ["browser_action"],
              title: "click A",
              id: "test-click",
            },
            () => {
              browser.test.sendMessage("create", browser.runtime.lastError?.message);
            }
          );
          browser.test.onMessage.addListener(msg => {
            browser.test.assertEq("add-again", msg, "expected msg");
            browser.menus.create(
              {
                contexts: ["browser_action"],
                title: "click A",
                id: "test-click",
              },
              () => {
                browser.test.assertEq(
                  "The menu id test-click already exists in menus.create.",
                  browser.runtime.lastError?.message,
                  "lastError message for missing id"
                );
                browser.test.sendMessage("done");
              }
            );
          });
        }'''), 'temporary')
        extension.startup()
        last_error = extension.await_message('create')
        self.is_(last_error, None, 'no error creating menu')
        extension.send_message('add-again')
        extension.await_message('done')
        extension.terminate_background()
        extension.wakeup_background()
        last_error = extension.await_message('create')
        self.is_(last_error, 'The menu id test-click already exists in menus.create.',
                 'lastError using duplicate ID')
        extension.unload()

        self.forbid_unchecked_last_error(since)

