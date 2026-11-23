"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_click_types.js.

The add-ons' code is Firefox's, as it is. clickPageAction() is a real click
on the page action's button in the location bar, with Firefox's button (0
left, 1 middle) and the modifier keys held (click_page_action()).
triggerPageActionWithKeyboard() gives the button the keyboard focus and
presses Enter with the modifiers held, as Firefox's focusButtonAndPressKey()
does (trigger_page_action_with_keyboard()): the browser's way to reach the
button with the keyboard is the toolbar's keyboard focus (Alt+Shift+T),
then Tab, until the button's focus ring shows. clickBrowserAction() is a
real click on the add-on's toolbar button. Firefox's metaKey is the Super
key; the test runs on Linux, so its macOS branch (MacCtrl) is left out.

The event page tasks: this browser has event pages without Firefox's pref
extensions.eventPages.enabled. The event page stops after Chromium's idle
time (terminate_background()), longer than the test's steps take, as
Firefox's: a stop between the clicks would start the background again, and
its "ready" message would be one more than Firefox's test awaits.

Left out:
- assertPersistentListeners(), which reads Gecko's primed listeners.
- clickPageActionInPanel() and triggerPageActionWithKeyboardInPanel(), which
  click the page action in Firefox's page actions panel, the location bar's
  "..." menu. Firefox hides that panel's button by default (the test's
  add_setup shows it again, bug 1704171), and this browser has no such
  panel: its page actions are buttons in the location bar only.
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


def click_page_action(test, extension, modifiers=None):
    """clickPageAction(extension, window, modifiers): a real click on the
    add-on's page action button with Firefox's `button` (0 left, 1 middle)
    and the keys of `modifiers` ({shiftKey: true, ...}) held."""
    modifiers = dict(modifiers or {})
    button = modifiers.pop('button', 0)
    view = head.wait_page_action_button(test, extension)
    keys = [head.MODIFIERS[name] for name, held in modifiers.items() if held]
    for key in keys:
        test.browser.xdotool('keydown', key)
    try:
        head.synthesize_mouse_at_center(test, view, button)
    finally:
        for key in reversed(keys):
            test.browser.xdotool('keyup', key)


def has_focus(test, view):
    """`view` has the keyboard focus: its focus ring (views' FocusRing, a
    child of the button over its bounds) shows only then."""
    box = view.bounds
    for ring in test.browser.views('FocusRing'):
        x, y = ring.center
        inside = box['x'] <= x < box['x'] + box['width'] and box['y'] <= y < box['y'] + box['height']
        if ring.visible and inside and ring.bounds['width'] < 2 * box['width']:
            return True
    return False


def trigger_page_action_with_keyboard(test, extension, modifiers=None):
    """triggerPageActionWithKeyboard(extension, modifiers): the add-on's page
    action button gets the keyboard focus, from the toolbar's (Alt+Shift+T)
    and Tab, and Enter is pressed with the keys of `modifiers` held; then the
    focus leaves the toolbar (Escape), as Firefox blurs the button."""
    button = head.wait_page_action_button(test, extension)
    test.browser.key('alt+shift+t')
    for _ in range(40):
        if has_focus(test, button):
            break
        test.browser.key('Tab')
    else:
        raise AssertionError("the page action button doesn't take the keyboard focus")
    keys = [head.MODIFIERS[name] for name, held in (modifiers or {}).items() if held]
    test.browser.key('+'.join([*keys, 'Return']))
    test.browser.key('Escape')


def await_click(extension):
    """extension.awaitMessage("onClick"): the OnClickData that the add-on
    sends, or {} where it sends none (pageAction.onClicked without an
    `info`), so that each check of it fails on its own."""
    return extension.await_message('onClick') or {}


def click_browser_action(test, extension):
    """clickBrowserAction(): a real click on the add-on's toolbar button."""
    test.browser.click_view(test.browser.toolbar_button(extension.id))


class PageActionClickTypesTest(FirefoxTest):

    def assert_single_modifier(self, info, modifier):
        """assertSingleModifier(), on Linux."""
        self.is_(len(info.get('modifiers') or []), 1,
                 'No unnecessary modifiers for exactly one key on event')
        self.is_((info.get('modifiers') or [None])[0], MAP[modifier],
                 'Correct modifier on click event')

    def click_page_action_tests(self, extension):
        """testClickPageAction(clickPageAction, triggerPageActionWithKeyboard)."""
        for modifier in MAP:
            for i in range(2):
                click_event_data = {'button': i, modifier: True}
                click_page_action(self, extension, click_event_data)
                info = await_click(extension)

                self.is_(info.get('button'), i, 'Correct button on click event')
                self.assert_single_modifier(info, modifier)

            trigger_page_action_with_keyboard(self, extension, {modifier: True})
            info = await_click(extension)

            self.is_(info.get('button'), 0, 'Key command emulates left click')
            self.assert_single_modifier(info, modifier)

    def run_click_data(self, test_as_non_persistent=False):
        """test_clickData()."""
        extension = self.load_extension(
            manifest={
                'page_action': {},
                'background': {
                    'persistent': not test_as_non_persistent,
                    'scripts': ['background.js'],
                },
            },

            files={
                'background.js': JS('''async function background() {
        function onClicked(_tab, info) {
          let button = info.button;
          let modifiers = info.modifiers;
          browser.test.sendMessage("onClick", { button, modifiers });
        }

        browser.pageAction.onClicked.addListener(onClicked);

        let [tab] = await browser.tabs.query({
          active: true,
          currentWindow: true,
        });
        await browser.pageAction.show(tab.id);
        browser.test.sendMessage("ready");
      }'''),
            })

        extension.startup()
        extension.await_message('ready')

        if test_as_non_persistent:
            # Terminating the background event page
            extension.terminate_background()

        # Clicking the pageAction
        self.click_page_action_tests(extension)

        if test_as_non_persistent:
            extension.await_message('ready')

        extension.unload()

    def run_click_data_reset(self, test_as_non_persistent=False):
        """test_clickData_reset()."""
        extension = self.load_extension(
            manifest={
                'browser_action': {
                    'default_area': 'navbar',
                },
                'page_action': {},
                'background': {
                    'persistent': not test_as_non_persistent,
                    'scripts': ['background.js'],
                },
            },

            files={
                'background.js': JS('''async function background() {
        function onBrowserActionClicked() {
          // openPopup requires user interaction, such as a browser action click.
          browser.pageAction.openPopup();
        }

        function onPageActionClicked(tab, info) {
          browser.test.sendMessage("onClick", info);
        }

        browser.browserAction.onClicked.addListener(onBrowserActionClicked);
        browser.pageAction.onClicked.addListener(onPageActionClicked);

        let [tab] = await browser.tabs.query({
          active: true,
          currentWindow: true,
        });
        await browser.pageAction.show(tab.id);
        browser.test.sendMessage("ready");
      }'''),
            })

        def click_page_action_with_modifiers():
            click_page_action(self, extension, {'button': 1, 'shiftKey': True})
            info = await_click(extension)
            self.is_(info.get('button'), 1, 'button')
            self.is_((info.get('modifiers') or [None])[0], 'Shift', 'modifiers[0]')

        def assert_info_reset(info):
            self.is_(info.get('button'), 0, 'ClickData button reset properly')
            # modifiers.length is 0: no modifiers, where the info has them.
            self.is_(info.get('modifiers'), [], 'ClickData modifiers reset properly')

        extension.startup()
        extension.await_message('ready')

        if test_as_non_persistent:
            # Terminating the background event page
            extension.terminate_background()

        # Clicking the pageAction
        click_page_action_with_modifiers()

        if test_as_non_persistent:
            extension.await_message('ready')

        click_browser_action(self, extension)
        assert_info_reset(await_click(extension))

        click_page_action_with_modifiers()

        trigger_page_action_with_keyboard(self, extension)
        assert_info_reset(await_click(extension))

        extension.unload()

    def test_01_clickData_MV2(self):
        self.run_click_data(test_as_non_persistent=False)

    def test_02_clickData_MV2_eventPage(self):
        self.run_click_data(test_as_non_persistent=True)

    def test_03_clickData_reset_MV2(self):
        self.run_click_data_reset(test_as_non_persistent=False)

    def test_04_clickData_reset_MV2_eventPage(self):
        self.run_click_data_reset(test_as_non_persistent=True)
