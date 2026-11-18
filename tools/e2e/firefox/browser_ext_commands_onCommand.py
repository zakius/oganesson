"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_commands_onCommand.js.

Firefox's `EventUtils.synthesizeKey()` is a real key press in the window that
has the focus, and `focusWindow()` activates the window's tab and gives its
page the keyboard focus, as Firefox's test does after it loads about:robots,
which this browser doesn't have: its windows show a page of their own. Firefox's
keysets are Gecko internals: the port leaves out their counts, and checks that
an add-on's shortcuts work in a window by pressing them. In the private window,
where Firefox's keyset is missing without the add-on's private access, the
port presses one of the shortcuts (Ctrl+A) and checks that no command comes,
and it leaves out the checks that the keysets go with the add-on. The console
warning for the unrecognized property is one of the add-on's install
warnings, which chrome://extensions shows. Left out of test_02_commands_event_page:
assertPersistentListeners(), which reads Gecko's primed listeners.
`terminateBackground()` is quick with EVENT_PAGE_ARGS.
"""

import re
import time

from firefox import head
from extension_test_utils import EVENT_PAGE_ARGS, JS, FirefoxTest
from harness import Page, wait_for

PAGE = 'data:text/html,<title>Robots</title><body style="height: 100vh">Robots</body>'

TEST_COMMANDS = [
    # Ctrl Shortcuts
    {
        'name': 'toggle-ctrl-a',
        'shortcut': 'Ctrl+A',
        'key': 'A',
        'modifiers': {
            'accelKey': True,
        },
    },
    {
        'name': 'toggle-ctrl-up',
        'shortcut': 'Ctrl+Up',
        'key': 'VK_UP',
        'modifiers': {
            'accelKey': True,
        },
    },
    # Alt Shortcuts
    {
        'name': 'toggle-alt-a',
        'shortcut': 'Alt+A',
        'key': 'A',
        'modifiers': {
            'altKey': True,
        },
    },
    {
        'name': 'toggle-alt-down',
        'shortcut': 'Alt+Down',
        'key': 'VK_DOWN',
        'modifiers': {
            'altKey': True,
        },
    },
    # Mac Shortcuts
    {
        'name': 'toggle-command-shift-page-up',
        'shortcutMac': 'Command+Shift+PageUp',
        'key': 'VK_PAGE_UP',
        'modifiers': {
            'accelKey': True,
            'shiftKey': True,
        },
    },
    {
        'name': 'toggle-mac-control-shift+period',
        'shortcut': 'Ctrl+Shift+Period',
        'shortcutMac': 'MacCtrl+Shift+Period',
        'key': 'VK_PERIOD',
        'modifiers': {
            'ctrlKey': True,
            'shiftKey': True,
        },
    },
    # Ctrl+Shift Shortcuts
    {
        'name': 'toggle-ctrl-shift-left',
        'shortcut': 'Ctrl+Shift+Left',
        'key': 'VK_LEFT',
        'modifiers': {
            'accelKey': True,
            'shiftKey': True,
        },
    },
    {
        'name': 'toggle-ctrl-shift-1',
        'shortcut': 'Ctrl+Shift+1',
        'key': '1',
        'modifiers': {
            'accelKey': True,
            'shiftKey': True,
        },
    },
    # Alt+Shift Shortcuts
    {
        'name': 'toggle-alt-shift-1',
        'shortcut': 'Alt+Shift+1',
        'key': '1',
        'modifiers': {
            'altKey': True,
            'shiftKey': True,
        },
    },
    {
        'name': 'toggle-alt-shift-a',
        'shortcut': 'Alt+Shift+A',
        'key': 'A',
        'modifiers': {
            'altKey': True,
            'shiftKey': True,
        },
    },
    {
        'name': 'toggle-alt-shift-right',
        'shortcut': 'Alt+Shift+Right',
        'key': 'VK_RIGHT',
        'modifiers': {
            'altKey': True,
            'shiftKey': True,
        },
    },
    # Function keys
    {
        'name': 'function-keys-Alt+Shift+F3',
        'shortcut': 'Alt+Shift+F3',
        'key': 'VK_F3',
        'modifiers': {
            'altKey': True,
            'shiftKey': True,
        },
    },
    {
        'name': 'function-keys-F2',
        'shortcut': 'F2',
        'key': 'VK_F2',
        'modifiers': {
            'altKey': False,
            'shiftKey': False,
        },
    },
    # Misc Shortcuts
    {
        'name': 'valid-command-with-unrecognized-property-name',
        'shortcut': 'Alt+Shift+3',
        'key': '3',
        'modifiers': {
            'altKey': True,
            'shiftKey': True,
        },
        'unrecognized_property': 'with-a-random-value',
    },
    {
        'name': 'spaces-in-shortcut-name',
        'shortcut': '  Alt + Shift + 2  ',
        'key': '2',
        'modifiers': {
            'altKey': True,
            'shiftKey': True,
        },
    },
    {
        'name': 'toggle-ctrl-space',
        'shortcut': 'Ctrl+Space',
        'key': 'VK_SPACE',
        'modifiers': {
            'accelKey': True,
        },
    },
    {
        'name': 'toggle-ctrl-comma',
        'shortcut': 'Ctrl+Comma',
        'key': 'VK_COMMA',
        'modifiers': {
            'accelKey': True,
        },
    },
    {
        'name': 'toggle-ctrl-period',
        'shortcut': 'Ctrl+Period',
        'key': 'VK_PERIOD',
        'modifiers': {
            'accelKey': True,
        },
    },
    {
        'name': 'toggle-ctrl-alt-v',
        'shortcut': 'Ctrl+Alt+V',
        'key': 'V',
        'modifiers': {
            'accelKey': True,
            'altKey': True,
        },
    },
]

# EventUtils' key names, as xdotool names them.
KEYS = {
    'VK_UP': 'Up', 'VK_DOWN': 'Down', 'VK_LEFT': 'Left', 'VK_RIGHT': 'Right',
    'VK_PAGE_UP': 'Prior', 'VK_PERIOD': 'period', 'VK_COMMA': 'comma', 'VK_SPACE': 'space',
    'VK_F2': 'F2', 'VK_F3': 'F3',
}
# EventUtils' modifiers; accelKey is Ctrl off macOS.
MODIFIERS = {'accelKey': 'ctrl', 'ctrlKey': 'ctrl', 'altKey': 'alt', 'shiftKey': 'shift'}

BACKGROUND = JS('''function background() {
  browser.commands.onCommand.addListener(async (commandName, tab) => {
    let [expectedTab] = await browser.tabs.query({
      currentWindow: true,
      active: true,
    });
    browser.test.assertEq(
      tab.id,
      expectedTab.id,
      "Expected onCommand listener to pass the current tab"
    );
    browser.test.sendMessage("oncommand", commandName);
  });
  browser.test.sendMessage("ready");
}''')


def synthesize_key(test, key, modifiers):
    """EventUtils.synthesizeKey(): the key, with its modifiers held, to the
    window that has the focus."""
    held = [MODIFIERS[name] for name, on in modifiers.items() if on]
    test.browser.xdotool('key', '+'.join([*held, KEYS.get(key, key.lower())]))


def focus_window(test, page):
    """focusWindow() and gBrowser.selectedBrowser.focus(): `page`'s tab is
    active, and its page has the keyboard focus (a click on it, where the
    location bar has it)."""
    test.browser.browser_call('Target.activateTarget', targetId=page.id)
    if not page.eval('document.hasFocus()'):
        test.browser.click_view(next(v for v in test.browser.views('ContentsWebView') if v.visible))
    wait_for(lambda: page.eval('document.hasFocus()'), what="the window's page to have the focus")


def open_window(test):
    """BrowserTestUtils.openNewBrowserWindow(), and PAGE loaded in it: its
    tab, once the page has loaded."""
    browser = test.browser
    target = browser.browser_call('Target.createTarget', url=PAGE, newWindow=True)['targetId']
    page = Page(wait_for(lambda: next((t for t in browser.targets() if t['id'] == target), None),
                         what='the new window'))
    wait_for(lambda: page.eval('document.readyState') == 'complete', what=f'{PAGE} to load')
    return page


class CommandsOnCommandTest(FirefoxTest):
    browser_args = (*FirefoxTest.browser_args, *EVENT_PAGE_ARGS)

    def run_commands(self, extension, page):
        focus_window(self, page)
        for test_command in TEST_COMMANDS:
            if test_command.get('shortcutMac') and not test_command.get('shortcut'):
                continue
            synthesize_key(self, test_command['key'], test_command['modifiers'])
            # Firefox's test waits on; the port notes the missing command and
            # goes on to the next.
            try:
                message = extension.await_message('oncommand', timeout=5)
            except AssertionError:
                message = None
            self.is_(message, test_command['name'],
                     f'Expected onCommand listener to fire with the correct name: {test_command["name"]}')

    def test_01_user_defined_commands(self):
        # Create a window before the extension is loaded.
        win1 = open_window(self)

        commands = {}
        for test_command in TEST_COMMANDS:
            command = {'suggested_key': {}}
            if test_command.get('shortcut'):
                command['suggested_key']['default'] = test_command['shortcut']
            if test_command.get('shortcutMac'):
                command['suggested_key']['mac'] = test_command['shortcutMac']
            if test_command.get('unrecognized_property'):
                command['unrecognized_property'] = test_command['unrecognized_property']
            commands[test_command['name']] = command

        extension = self.load_extension(manifest={'commands': commands}, background=BACKGROUND)
        extension.startup()
        extension.await_message('ready')

        warnings = self.browser.extension_info(extension.id)['installWarnings']
        self.check(any(re.search(r'Reading manifest: Warning processing commands.*.unrecognized_property: '
                                 'An unexpected property was found', w) for w in warnings),
                   f'the unrecognized property is warned about - Actual: {warnings}')

        # Create another window after the extension is loaded.
        win2 = open_window(self)

        # Confirm that the commands are registered to both windows.
        self.run_commands(extension, win1)
        self.run_commands(extension, win2)

        private_tab = head.open_private_window(self)
        self.load_url(private_tab, PAGE)
        self.watch(private_tab)

        # Expected keyset is not added to private windows
        focus_window(self, private_tab)
        synthesize_key(self, 'A', {'accelKey': True})
        time.sleep(2)
        self.read_reports()
        self.is_(extension.messages, [], 'Expected no command in the private window')

        extension.unload()

        # Test that given permission the keyset is added to the private window.
        extension = self.load_extension(manifest={'commands': commands}, background=BACKGROUND,
                                        incognito_override='spanning')
        extension.startup()
        extension.await_message('ready')

        self.run_commands(extension, win1)
        self.run_commands(extension, win2)
        self.run_commands(extension, private_tab)

        extension.unload()

        for page in (win1, win2, private_tab):
            head.close_window(self, head.window_of(self, page))

    def test_02_commands_event_page(self):
        extension = self.load_extension(
            use_addon_manager='permanent',
            manifest={
                'browser_specific_settings': {'gecko': {'id': 'eventpage@commands'}},
                'background': {'persistent': False},
                'commands': {
                    'toggle-feature': {
                        'suggested_key': {
                            'default': 'Alt+Shift+J',
                        },
                    },
                },
            },
            background=JS('''function() {
              browser.commands.onCommand.addListener((name, tab) => {
                browser.test.assertEq(name, "toggle-feature", "command received");
                browser.test.assertTrue(!!tab, "tab received");
                browser.test.sendMessage("onCommand");
              });
              browser.test.sendMessage("ready");
            }'''))

        extension.startup()
        extension.await_message('ready')

        # test events waken background
        extension.terminate_background()

        self.browser.key('alt+shift+j')

        extension.await_message('ready')
        extension.await_message('onCommand')
        # persistent event woke background

        extension.unload()
