"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_incognito.js.

Firefox's item IDs (`<widget id>-menuitem-<id>`) are Gecko's DOM: the port
finds each add-on's item by its label, as each label names its add-on.
Firefox's Tools menu is the app menu's More tools (head.open_tools_menu()),
and its private window's first page, about:privatebrowsing, is this
browser's private new tab page. file_dummy.html is served over plain HTTP,
as the menus port serves example.com. A `viewType` that is undefined is
left out of an expected event, as a message drops it. The pref that keeps
a right click from selecting a word is macOS's: this browser doesn't select
one on Linux.
"""

from firefox import head
from extension_test_utils import JS

DUMMY_PATH = f'{head.DIR}file_dummy.html'
DUMMY_HTML = b'''<html>
<head>
<title>Dummy test page</title>
<meta http-equiv="Content-Type" content="text/html;charset=utf-8"></meta>
</head>
<body>
<p>Dummy test page</p>
<a id="link_to_example_com" href="https://example.com/#linkclick">link</a>
</body>
</html>
'''

BACKGROUND = JS('''function background() {
  let events = [];
  browser.menus.onShown.addListener(data => events.push(data));
  browser.menus.onHidden.addListener(() => events.push("onHidden"));
  browser.test.onMessage.addListener(async (name, data) => {
    if (name == "check-events") {
      browser.test.sendMessage("events", events);
      events = [];
    }
    if (name == "create-menu") {
      let id = await new Promise(resolve => {
        let mid = browser.menus.create(data, () => resolve(mid));
      });
      browser.test.sendMessage("menu-id", id);
    }
  });
}''')


class MenusIncognitoTest(head.ContextMenuTest):
    hosts = ('mochi.test', 'example.com')
    routes = {**head.ROUTES,
              DUMMY_PATH: (200, {'Content-Type': 'text/html'}, DUMMY_HTML)}

    def check_events(self, ext, expected):
        ext.send_message('check-events')
        events = ext.await_message('events')
        self.check(events == expected,
                   f'expected events received for {ext.id}. - Expected: {expected}, Actual: {events}')

    def has_item(self, menu, label, message):
        self.check(bool(menu.by_label(label)), message)

    def has_no_item(self, menu, label, message):
        self.check(not menu.by_label(label), message)

    # Make sure that we won't trigger events for a private window.
    def test_01_no_show_hide_for_private_window(self):
        pb_extension = self.load_extension(
            background=BACKGROUND,
            manifest={
                'browser_specific_settings': {
                    'gecko': {'id': '@private-allowed'},
                },
                'permissions': ['menus', 'tabs'],
            },
            incognito_override='spanning')

        extension = self.load_extension(
            background=BACKGROUND,
            manifest={
                'browser_specific_settings': {
                    'gecko': {'id': '@not-allowed'},
                },
                'permissions': ['menus', 'tabs'],
            })

        pb_extension.startup()
        extension.startup()

        extension.send_message('create-menu', {
            'title': 'not_allowed',
            'contexts': ['all', 'tools_menu'],
        })
        id1 = extension.await_message('menu-id')
        pb_extension.send_message('create-menu', {
            'title': 'spanning_allowed',
            'contexts': ['all', 'tools_menu'],
        })
        id2 = pb_extension.await_message('menu-id')

        # Expected menu events
        base_shown_event = {
            'contexts': ['page', 'all'],
            'viewType': 'tab',
            'frameId': 0,
            'editable': False,
        }
        public_shown = {'menuIds': [id1], **base_shown_event}
        private_shown = {'menuIds': [id2], **base_shown_event}

        base_shown_event = {
            'contexts': ['tools_menu'],
            'editable': False,
        }
        tools_shown = {'menuIds': [id1], **base_shown_event}
        private_tools_shown = {'menuIds': [id2], **base_shown_event}

        # Run tests in non-private window

        tab = self.open_tab(f'http://example.com{DUMMY_PATH}')

        # Open and close a menu on the public window.
        menu = head.open_context_menu(self, tab, 'p')

        # We naturally expect both extensions here.
        self.has_item(menu, 'not_allowed', 'menu exists not_allowed')
        self.has_item(menu, 'spanning_allowed', 'menu exists spanning_allowed')
        head.close_context_menu(self)

        self.check_events(extension, [public_shown, 'onHidden'])
        self.check_events(pb_extension, [private_shown, 'onHidden'])

        menu = head.open_tools_menu(self)
        self.has_item(menu, 'not_allowed', 'menu exists not_allowed')
        self.has_item(menu, 'spanning_allowed', 'menu exists spanning_allowed')
        head.close_context_menu(self)

        self.check_events(extension, [tools_shown, 'onHidden'])
        self.check_events(pb_extension, [private_tools_shown, 'onHidden'])

        # Run tests on private window

        private_tab = head.open_private_window(self)
        private_window = head.window_of(self, private_tab)

        # Open and close a menu on the private window.
        menu = head.open_context_menu(self, private_tab, 'body div')
        # We should not see the "not_allowed" extension here.
        self.has_no_item(menu, 'not_allowed', 'menu does not exist not_allowed in private window')
        self.has_item(menu, 'spanning_allowed', 'menu exists spanning_allowed in private window')
        head.close_context_menu(self)

        self.check_events(extension, [])
        self.check_events(pb_extension, [private_shown, 'onHidden'])

        menu = head.open_tools_menu(self)
        # We should not see the "not_allowed" extension here.
        self.has_no_item(menu, 'not_allowed', 'menu does not exist not_allowed in private window')
        self.has_item(menu, 'spanning_allowed', 'menu exists spanning_allowed in private window')
        head.close_context_menu(self)

        self.check_events(extension, [])
        self.check_events(pb_extension, [private_tools_shown, 'onHidden'])

        extension.unload()
        pb_extension.unload()
        self.browser.close_target(tab)
        head.close_window(self, private_window)
