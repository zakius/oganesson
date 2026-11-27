"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_browserAction_click_types.js.

The add-ons' code is Firefox's, as it is. test_clickData()'s areas are the
add-on pinned to the toolbar (CustomizableUI's navigation bar) or unpinned
into the Extensions menu (the add-ons panel), as the user does on its page in
chrome://extensions (head.pin_to_toolbar()). clickBrowserAction() is a real
click on the add-on's toolbar button, or on its row in the Extensions menu
that the toolbar's Extensions button opens, with Firefox's button (0 left, 1
middle) and the modifier keys held (click_browser_action()).
triggerBrowserActionWithKeyboard() gives the button the keyboard focus and
presses a key with the modifiers held (trigger_browser_action_with_keyboard()):
in the toolbar, the toolbar's keyboard focus (Alt+Shift+T), then Tab, until
the button's focus ring shows; in the Extensions menu, the pointer over the
add-on's row, which takes the focus then, as the arrow keys give it in
Firefox. Firefox presses Space; the port presses Enter, which clicks a
focused button here as Space does, because a toolbar button leaves Alt+Space
to the window (views' MenuButtonController). clickPageAction() is a real
click on the page action's button in the location bar
(head.click_page_action()). Firefox's metaKey is the Super key; the test
runs on Linux, so its macOS branch (MacCtrl) is left out.

The event page tasks: this browser has event pages without Firefox's pref
extensions.eventPages.enabled. The event page stops after Chromium's idle
time (terminate_background()). A Manifest V3 add-on's background scripts are
an event page in Firefox.

Left out: assertPersistentListeners(), which reads Gecko's primed listeners.
"""

from extension_test_utils import JS, FirefoxTest
from firefox import head

# Firefox's map of the modifiers to OnClickData's names.
MAP = {
    'shiftKey': 'Shift',
    'altKey': 'Alt',
    'metaKey': 'Command',
    'ctrlKey': 'Ctrl',
}

NAME = 'Generated extension'


def browser_action_button(test, extension, pinned):
    """The add-on's button: in the toolbar (`pinned`), or its row in the
    Extensions menu, which this opens."""
    if pinned:
        return test.browser.toolbar_button(extension.id)
    try:
        head.open_extensions_panel(test, timeout=3)
    except AssertionError:
        # Alt released after a click with no key in between moves the
        # keyboard focus to the toolbar, as in Chromium; the next click only
        # ends that, so the menu needs a second one.
        head.open_extensions_panel(test)
    return test.browser.wait_view('ExtensionsMenuButton', Text=NAME)


def held_keys(modifiers):
    """xdotool's names of the keys of Firefox's `modifiers` ({shiftKey: true,
    ...})."""
    return [head.MODIFIERS[name] for name, held in modifiers.items() if held]


def click_browser_action(test, extension, pinned, modifiers=None):
    """clickBrowserAction(extension, window, modifiers): a real click on the
    add-on's button with Firefox's `button` (0 left, 1 middle) and the keys of
    `modifiers` held. In the Extensions menu, the menu closes again."""
    modifiers = dict(modifiers or {})
    button = modifiers.pop('button', 0)
    view = browser_action_button(test, extension, pinned)
    keys = held_keys(modifiers)
    for key in keys:
        test.browser.xdotool('keydown', key)
    try:
        head.synthesize_mouse_at_center(test, view, button)
    finally:
        for key in reversed(keys):
            test.browser.xdotool('keyup', key)
    if not pinned:
        head.close_extensions_panel(test)


def trigger_browser_action_with_keyboard(test, extension, pinned, modifiers=None):
    """triggerBrowserActionWithKeyboard(extension, key, modifiers): the
    add-on's button gets the keyboard focus, and Enter is pressed with the
    keys of `modifiers` held; then the focus leaves the toolbar (Escape), as
    Firefox blurs the button, or the Extensions menu closes."""
    view = browser_action_button(test, extension, pinned)
    combo = '+'.join([*held_keys(modifiers or {}), 'Return'])
    if pinned:
        head.focus_toolbar_view(test, view)
        test.browser.key(combo)
        test.browser.key('Escape')
        return
    # The menu has the keyboard focus: a key to the browser window would
    # close it first.
    x, y = view.center
    test.browser.xdotool('mousemove', str(x), str(y))
    test.browser.xdotool('key', combo)
    head.close_extensions_panel(test)


def await_click(extension):
    """extension.awaitMessage("onClick"): the OnClickData that the add-on
    sends, or {} where it sends none (onClicked without an `info`), so that
    each check of it fails on its own."""
    return extension.await_message('onClick') or {}


class BrowserActionClickTypesTest(FirefoxTest):

    def assert_single_modifier(self, info, modifier, area):
        """assertSingleModifier(), on Linux."""
        self.is_(len(info.get('modifiers') or []), 1,
                 'No unnecessary modifiers for exactly one key on event')
        self.is_((info.get('modifiers') or [None])[0], MAP[modifier],
                 f'Correct modifier on {area} click')

    def run_click_data(self, manifest_version, persistent=None):
        """test_clickData({manifest_version, persistent})."""
        action = 'browser_action' if manifest_version < 3 else 'action'
        background = {'scripts': ['background.js']}

        if persistent is not None:
            background['persistent'] = persistent

        extension = self.load_extension(
            manifest={
                'manifest_version': manifest_version,
                action: {},
                'background': background,
            },

            files={
                'background.js': JS('''function backgroundScript() {
        function onClicked(tab, info) {
          let button = info.button;
          let modifiers = info.modifiers;
          browser.test.sendMessage("onClick", { button, modifiers });
        }

        const apiNS =
          browser.runtime.getManifest().manifest_version >= 3
            ? "action"
            : "browserAction";

        browser[apiNS].onClicked.addListener(onClicked);
        browser.test.sendMessage("ready");
      }'''),
            })

        extension.startup()
        extension.await_message('ready')

        if manifest_version >= 3 or persistent is False:
            extension.terminate_background()

        for pinned, area in ((True, 'nav-bar'), (False, 'unified-extensions-area')):
            head.pin_to_toolbar(self, extension, pinned)

            for modifier in MAP:
                for i in range(2):
                    click_event_data = {'button': i, modifier: True}
                    click_browser_action(self, extension, pinned, click_event_data)
                    details = await_click(extension)

                    self.is_(details.get('button'), i, f'Correct button in {area} click')
                    self.assert_single_modifier(details, modifier, area)

                trigger_browser_action_with_keyboard(self, extension, pinned, {modifier: True})
                details = await_click(extension)

                self.is_(details.get('button'), 0, 'Key command emulates left click')
                self.assert_single_modifier(details, modifier, area)

        if manifest_version >= 3 or persistent is False:
            # The background event page is expected to have been
            # spawned again to handle the action onClicked event.
            extension.await_message('ready')

        extension.unload()

    def run_click_data_reset(self, manifest_version):
        """test_clickData_reset({manifest_version})."""
        action = 'browser_action' if manifest_version < 3 else 'action'
        browser_action_command = ('_execute_browser_action' if manifest_version < 3
                                  else '_execute_action')
        extension = self.load_extension(
            manifest={
                'manifest_version': manifest_version,
                action: {
                    'default_area': 'navbar',
                },
                'page_action': {},
                'commands': {
                    browser_action_command: {
                        'suggested_key': {
                            'default': 'Alt+Shift+J',
                        },
                    },
                },
            },

            background=JS('''async function background() {
      function onBrowserActionClicked(tab, info) {
        browser.test.sendMessage("onClick", info);
      }

      function onPageActionClicked() {
        browser.test.sendMessage("open-popup");
      }

      const { manifest_version } = browser.runtime.getManifest();
      const apiNS = manifest_version >= 3 ? "action" : "browserAction";

      browser[apiNS].onClicked.addListener(onBrowserActionClicked);

      // pageAction should only be available in MV2 extensions.
      if (manifest_version < 3) {
        browser.pageAction.onClicked.addListener(onPageActionClicked);

        let [tab] = await browser.tabs.query({
          active: true,
          currentWindow: true,
        });
        await browser.pageAction.show(tab.id);
      }

      browser.test.sendMessage("ready");
    }'''))

        # Pollute the state of the browserAction's lastClickInfo
        def click_browser_action_with_modifiers():
            click_browser_action(self, extension, True, {'button': 1, 'shiftKey': True})
            info = await_click(extension)
            self.is_(info.get('button'), 1, 'Got expected ClickData button details')
            self.is_((info.get('modifiers') or [None])[0], 'Shift',
                     'Got expected ClickData modifiers details')

        def assert_info_reset(info):
            self.is_(info.get('button'), 0, 'ClickData button reset properly')
            # modifiers.length is 0: no modifiers, where the info has them.
            self.is_(info.get('modifiers'), [], 'ClickData modifiers reset properly')

        extension.startup()
        extension.await_message('ready')

        if manifest_version >= 3:
            extension.terminate_background()

        click_browser_action_with_modifiers()

        if manifest_version >= 3:
            # The background event page is expected to have been
            # spawned again to handle the action onClicked event.
            extension.await_message('ready')
        else:
            extension.on_message('open-popup', lambda: self.browser.key('alt+shift+j'))

            # pageAction should only be available in MV2 extensions.
            head.click_page_action(self, extension)

            # NOTE: the pageAction event listener then triggers browserAction.onClicked
            assert_info_reset(await_click(extension))

        click_browser_action_with_modifiers()

        trigger_browser_action_with_keyboard(self, extension, True)
        assert_info_reset(await_click(extension))

        click_browser_action_with_modifiers()

        trigger_browser_action_with_keyboard(self, extension, True)
        assert_info_reset(await_click(extension))

        extension.unload()

    def test_01_clickData_MV2(self):
        self.run_click_data(manifest_version=2)

    def test_02_clickData_MV2_eventpage(self):
        self.run_click_data(manifest_version=2, persistent=False)

    def test_03_clickData_MV3(self):
        self.run_click_data(manifest_version=3)

    def test_04_clickData_reset_MV2(self):
        self.run_click_data_reset(manifest_version=2)

    def test_05_clickData_reset_MV3(self):
        self.run_click_data_reset(manifest_version=3)
