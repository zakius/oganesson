"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_startup_restored.js.

Firefox's test installs the menu add-ons with the add-on manager
(`useAddonManager: "permanent"`) only to disable and enable one; here every
add-on that a test loads can be, so the port loads them as it loads the
control add-on, while the browser runs. The harness's permanent add-ons
restart the browser, which Firefox's test doesn't, and which would take the
control add-on away. The add-on manager's disable() and enable() are
`management.setEnabled()` from chrome://extensions. Firefox's button ID
(`<widget id>-browser-action`) is Gecko's DOM: the port looks for the menu
add-on's toolbar button by its place among the pinned add-ons, since the
add-ons share their name, and pins it, as Firefox's `default_area` puts it
on the toolbar. Firefox checks the button at once; the port waits a few
seconds for the toolbar to change.
"""

from firefox import head
from extension_test_utils import JS
from harness import wait_for

NAME = 'Generated extension'


class MenusStartupRestoredTest(head.ContextMenuTest):

    def get_menu_extension(self, gecko_id, background):
        return self.load_extension(
            manifest={
                'manifest_version': 3,
                'browser_specific_settings': {'gecko': {'id': gecko_id}},
                'action': {
                    'default_area': 'navbar',
                },
                'permissions': ['menus'],
            },
            background=background)

    def button_shown(self):
        """The menu add-on's toolbar button is there. The add-ons share
        their name, so it is found by its place among the pinned add-ons,
        as Browser.toolbar_button() finds it."""
        pinned = self.browser.profile_prefs()['extensions']['pinned_extensions']['value']
        buttons = sorted((view for view in self.browser.views('ToolbarActionView') if view.visible),
                         key=lambda view: view.bounds['x'])
        if self.menu_id not in pinned or len(buttons) < len(pinned):
            return False
        return NAME in buttons[pinned.index(self.menu_id)].props.values()

    def check_button(self, shown, message):
        """Assert.ok() on the menu add-on's toolbar button being there, or
        gone. toolbar_button() pins it first, as Firefox's `default_area:
        "navbar"` puts it on the toolbar."""
        try:
            if shown:
                self.browser.toolbar_button(self.menu_id)
            else:
                wait_for(lambda: not self.button_shown(), timeout=5, interval=0.5, what=message)
        except AssertionError:
            self.check(False, message)

    def menu_labels(self, extension):
        menu = head.open_action_context_menu(self, extension, 'browser')
        return [head.label_of(item) for item in menu.items]

    def test_01_menu_create_id(self):
        # Create a control extension to be able to communicate with the menu extension
        # after it has been disabled and re-enabled again.
        control_extension = self.load_extension(
            manifest={
                'browser_specific_settings': {'gecko': {'id': 'control@mochi.test'}},
            },
            background=JS('''() => {
              browser.runtime.onMessageExternal.addListener(message =>
                browser.test.sendMessage(message)
              );
              browser.test.sendMessage("ready");
            }'''))
        control_extension.startup()
        control_extension.await_message('ready')

        # Create a manifest V3 extension, which adds its menu entries only in an
        # onInstalled listener.
        menu_extension = self.get_menu_extension('menu@mochi.test', JS('''() => {
          browser.runtime.onInstalled.addListener(() => {
            browser.menus.create(
              {
                id: "testItem",
                contexts: ["action"],
                title: "testItem",
              },
              () => {
                browser.runtime.sendMessage("control@mochi.test", "installed");
              }
            );
          });
          browser.runtime.sendMessage("control@mochi.test", "done");
        }'''))
        menu_extension.startup()
        self.menu_id = menu_extension.id
        control_extension.await_message('done')
        control_extension.await_message('installed')

        # Check if the action button and the context menu entry have been added.
        self.check_button(True, 'Button should have been created')
        self.check('testItem' in self.menu_labels(menu_extension),
                   'Context menu should have been created')
        head.close_context_menu(self)

        # Disable the extension and check that the action button has been removed.
        head.set_enabled(self, menu_extension, False)
        self.check_button(False, 'Button should have been removed')

        # Re-enable the extension and check, that the menu entry is correctly restored.
        head.set_enabled(self, menu_extension, True)
        control_extension.await_message('done')
        self.check_button(True, 'Button should have been re-created')
        self.check('testItem' in self.menu_labels(menu_extension),
                   'Context menu should have been restored')
        head.close_context_menu(self)

        # Uninstall the menu extension and check that the action button has been re-
        # moved.
        menu_extension.unload()
        self.check_button(False, 'Button should have been removed')

        # Install the menu extension again, but do not add a menu entry this time.
        # Verify that the startup cache has been cleared on uninstall and the no longer
        # existing menu entry has not been restored.
        no_menu_extension = self.get_menu_extension('menu@mochi.test', JS('''() => {
          browser.runtime.sendMessage("control@mochi.test", "done");
        }'''))
        no_menu_extension.startup()
        self.menu_id = no_menu_extension.id
        control_extension.await_message('done')
        self.check_button(True, 'Button should have been re-created')
        self.check('testItem' not in self.menu_labels(no_menu_extension),
                   'Context menu should not have been restored')
        head.close_context_menu(self)

        # Cleanup.
        no_menu_extension.unload()
        control_extension.unload()
