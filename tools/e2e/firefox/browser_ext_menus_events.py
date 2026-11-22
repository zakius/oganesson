"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_events.js.

add_setup()'s two tabs are opened by each task: a blank tab for Firefox's
someOtherTab, then testTab. The macOS pref of right clicks that select the
word under the cursor is left out: Linux has no such setting. Firefox's
ExtensionPermissions.add() of the optional host permission is the add-on's
permissions.request() from its background, with a user gesture, and the
user's Allow in the prompt (grant_optional_permission()). The tasks' page
changes and Firefox's frame ID of the page's frame
(WebNavigationFrames.getFrameId()) run in the page, and through a helper
add-on with the webNavigation permission (frame_id()). Firefox's popup is
the add-on's popup (Browser.open_popup()), and its pageUrl the popup's
chrome-extension: URL for Firefox's moz-extension: one. The page action's
tasks right-click the page action's button (head.open_action_context_menu());
the Tools menu's, the add-on's items in More tools (zakius/oganesson#98). This browser has no
list of all tabs with a tab menu, Firefox's all-tabs panel: that task fails.
An onShown info that a task doesn't expect at all, as when no menu fired
it, ends the task at the next await.
"""

import json

from firefox import head
from extension_test_utils import JS
from harness import wait_for

PAGE = f'{head.BASE}context.html'
PAGE_BASE = head.BASE
PAGE_HOST_PATTERN = 'http://mochi.test/*'

EXPECT_TARGET_ELEMENT = 13337

# testShowHideEvent()'s add-on, as Firefox has it.
BACKGROUND = '''async function background(menu_create_params) {
  const [tab] = await browser.tabs.query({
    active: true,
    currentWindow: true,
  });
  if (browser.pageAction) {
    await browser.pageAction.show(tab.id);
  }

  let shownEvents = [];
  let hiddenEvents = [];

  browser.menus.onShown.addListener((...args) => {
    browser.test.log(`==> onShown args ${JSON.stringify(args)}`);
    let [info, shownTab] = args;
    if (info.targetElementId) {
      // In this test, we aren't interested in the exact value,
      // only in whether it is set or not.
      info.targetElementId = 13337; // = EXPECT_TARGET_ELEMENT
    }
    shownEvents.push(info);

    if (menu_create_params.title.includes("TEST_EXPECT_NO_TAB")) {
      browser.test.assertEq(undefined, shownTab, "expect no tab");
    } else {
      browser.test.assertEq(tab.id, shownTab?.id, "expected tab");
    }
    browser.test.assertEq(2, args.length, "expected number of onShown args");
  });
  browser.menus.onHidden.addListener(event => hiddenEvents.push(event));

  browser.test.onMessage.addListener(async msg => {
    switch (msg) {
      case "register-menu": {
        let menuId;
        await new Promise(resolve => {
          menuId = browser.menus.create(menu_create_params, resolve);
        });
        browser.test.assertEq(
          0,
          shownEvents.length,
          "no onShown before menu"
        );
        browser.test.assertEq(
          0,
          hiddenEvents.length,
          "no onHidden before menu"
        );
        browser.test.sendMessage("menu-registered", menuId);
        break;
      }
      case "assert-menu-shown":
        browser.test.assertEq(1, shownEvents.length, "expected onShown");
        browser.test.assertEq(
          0,
          hiddenEvents.length,
          "no onHidden before closing"
        );
        browser.test.sendMessage("onShown-event-data", shownEvents[0]);
        break;
      case "assert-menu-hidden":
        browser.test.assertEq(
          1,
          shownEvents.length,
          "expected no more onShown"
        );
        browser.test.assertEq(1, hiddenEvents.length, "expected onHidden");
        browser.test.sendMessage("onHidden-event-data", hiddenEvents[0]);
        break;
      case "optional-menu-shown-with-permissions":
        browser.test.assertEq(
          2,
          shownEvents.length,
          "expected second onShown"
        );
        browser.test.sendMessage("onShown-event-data2", shownEvents[1]);
        break;
    }
  });

  browser.test.sendMessage("ready");
}'''


def grant_optional_permission(test, extension, origins):
    """grantOptionalPermission(): the add-on asks for `origins` with
    permissions.request(), as after a click, and the user allows them."""
    page = test.browser.extension_background(extension.id)
    try:
        page.call('Runtime.evaluate', userGesture=True,
                  expression=f'chrome.permissions.request({{origins: {json.dumps(origins)}}})'
                             '.then(granted => globalThis.__fxtestGranted = granted)')
        # The prompt ignores clicks for a moment after it shows (Chromium's
        # InputEventActivationProtector), so Allow is clicked until it closes.
        test.browser.wait_view('MdTextButton', Text='Allow')

        def allowed():
            buttons = [view for view in test.browser.views('MdTextButton', Text='Allow')
                       if view.visible]
            if buttons:
                test.browser.click_view(buttons[0])
            return not buttons
        wait_for(allowed, interval=0.5, what='the prompt to take the click on Allow')
        wait_for(lambda: page.eval('globalThis.__fxtestGranted === true', gesture=False),
                 what='the optional permission')
    finally:
        page.close()


class MenusEventsTest(head.ContextMenuTest):

    def setUp(self):
        super().setUp()
        self.some_other_tab = self.open_tab('about:blank')
        self.test_tab = self.open_tab(PAGE)

    def tearDown(self):
        try:
            for tab in (self.test_tab, self.some_other_tab):
                self.browser.close_target(tab)
        finally:
            super().tearDown()

    def switch_tab(self, tab):
        """BrowserTestUtils.switchTab()."""
        self.browser.browser_call('Target.activateTarget', targetId=tab.id)
        wait_for(lambda: tab.eval('document.visibilityState', gesture=False) == 'visible',
                 what='the tab to be selected')

    def frame_id(self):
        """WebNavigationFrames.getFrameId() of the test page's frame: the
        frameId that webNavigation gives it, asked of a helper add-on."""
        helper = self.load_extension(
            manifest={'permissions': ['webNavigation']},
            background=JS('''function background() {
              browser.test.onMessage.addListener(async () => {
                const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
                const frames = await browser.webNavigation.getAllFrames({ tabId: tab.id });
                const frame = frames.find(f => f.url.endsWith("context_frame.html"));
                browser.test.sendMessage("frameId", frame.frameId);
              });
            }'''))
        helper.startup()
        helper.send_message('frameId')
        frame_id = helper.await_message('frameId')
        helper.unload()
        return frame_id

    def show_hide_event(self, menu_create_params, open_menu, close_menu, expected_shown_event,
                        expected_shown_event_with_permissions=None,
                        force_tab_to_background=False, manifest_version=2, id=None):
        """testShowHideEvent(). An expected info may be a function of the
        add-on, for the values that Firefox's getters read."""
        # Tab must initially open as a foreground tab, because the test
        # extension looks for the active tab.
        self.switch_tab(self.test_tab)

        action = 'browser_action' if manifest_version < 3 else 'action'
        manifest = {
            'manifest_version': manifest_version,
            'page_action': {},
            action: {
                'default_popup': 'popup.html',
                'default_area': 'navbar',
            },
            'permissions': ['menus'],
            'optional_permissions': [PAGE_HOST_PATTERN],
        }
        use_addon_manager = None
        # hook up AOM so event pages in MV3 work.
        if manifest_version > 2:
            manifest['browser_specific_settings'] = {'gecko': {'id': id}}
            use_addon_manager = 'temporary'
        extension = self.load_extension(
            background=JS(BACKGROUND, json.dumps(menu_create_params)),
            use_addon_manager=use_addon_manager,
            manifest=manifest,
            files={
                'popup.html': '<!DOCTYPE html><meta charset="utf-8">Popup body',
            })
        extension.startup()
        extension.await_message('ready')
        extension.send_message('register-menu')
        menu_id = extension.await_message('menu-registered')

        if force_tab_to_background:
            self.switch_tab(self.some_other_tab)

        def expected(info):
            info = info(extension) if callable(info) else dict(info)
            # menuCreateParams.id is not set, therefore a numeric ID is generated.
            info['menuIds'] = [menu_id]
            return info

        open_menu(extension)
        extension.send_message('assert-menu-shown')
        shown_event = extension.await_message('onShown-event-data')
        self.is_(shown_event, expected(expected_shown_event), 'expected onShown info')

        close_menu(extension)
        extension.send_message('assert-menu-hidden')
        hidden_event = extension.await_message('onHidden-event-data')
        self.is_(hidden_event, None, 'expected no event data for onHidden event')

        if expected_shown_event_with_permissions:
            grant_optional_permission(self, extension, [PAGE_HOST_PATTERN])
            open_menu(extension)
            extension.send_message('optional-menu-shown-with-permissions')
            shown_event2 = extension.await_message('onShown-event-data2')
            self.is_(shown_event2, expected(expected_shown_event_with_permissions),
                     'expected onShown info when host permissions are enabled')
            close_menu(extension)

        extension.unload()

    def open_page_menu(self, selector, frame_index=None):
        return lambda extension: head.open_context_menu(self, self.test_tab, selector, frame_index)

    def close_menu(self, extension):
        head.close_extension_context_menu(self)

    # Make sure that we won't trigger onShown when extensions cannot add menus.
    def test_01_no_show_hide_for_unsupported_menu(self):
        extension = self.load_extension(
            background=JS('''function background() {
              let events = [];
              browser.menus.onShown.addListener(data => events.push(data));
              browser.menus.onHidden.addListener(() => events.push("onHidden"));
              browser.test.onMessage.addListener(() => {
                browser.test.assertEq(
                  "[]",
                  JSON.stringify(events),
                  "Should not have any events when the context is unsupported."
                );
                browser.test.notifyPass("done listening to menu events");
              });
            }'''),
            manifest={
                'permissions': ['menus'],
            })

        extension.startup()
        # Open and close a menu for which the extension cannot add menu items:
        # the reload button's, where this browser has one.
        self.browser.click_view(self.browser.wait_view('ReloadButton'), button=3)
        head.close_context_menu(self)

        extension.send_message('check menu events')
        extension.await_finish('done listening to menu events')

        extension.unload()

    def test_02_show_hide_without_menu_item(self):
        extension = self.load_extension(
            background=JS('''function background() {
              let events = [];
              browser.menus.onShown.addListener(data => events.push(data));
              browser.menus.onHidden.addListener(() => events.push("onHidden"));
              browser.test.onMessage.addListener(() => {
                browser.test.sendMessage("events from menuless extension", events);
              });

              browser.menus.create({
                title: "never shown",
                documentUrlPatterns: ["*://url-pattern-that-never-matches/*"],
                contexts: ["all"],
              });
            }'''),
            manifest={
                'permissions': ['menus', PAGE_HOST_PATTERN],
            })

        extension.startup()

        # Run another context menu test where onShown/onHidden will fire.
        self.show_hide_event(
            menu_create_params={
                'title': 'any menu item',
                'contexts': ['all'],
            },
            expected_shown_event={
                'contexts': ['page', 'all'],
                'viewType': 'tab',
                'editable': False,
                'frameId': 0,
            },
            open_menu=self.open_page_menu('body'),
            close_menu=self.close_menu)

        # Now the menu has been shown and hidden, and in another extension the
        # onShown/onHidden events have been dispatched.
        extension.send_message('check menu events')
        events = extension.await_message('events from menuless extension')
        self.is_(len(events), 2, 'expect two events')
        self.is_(events[1], 'onHidden', 'last event should be onHidden')
        self.check(bool(events[0].get('targetElementId')),
                   'info.targetElementId must be set in onShown')
        events[0].pop('targetElementId', None)
        self.is_(events[0], {
            'menuIds': [],
            'contexts': ['page', 'all'],
            'viewType': 'tab',
            'editable': False,
            'pageUrl': PAGE,
            'frameId': 0,
        }, 'expected onShown info from menuless extension')
        extension.unload()

    def page_action_task(self, **kwargs):
        self.show_hide_event(
            menu_create_params={
                'title': 'pageAction item',
                'contexts': ['page_action'],
                **kwargs.pop('menu_create_params', {}),
            },
            expected_shown_event={
                'contexts': ['page_action', 'all'],
                'editable': False,
            },
            expected_shown_event_with_permissions={
                'contexts': ['page_action', 'all'],
                'editable': False,
                'pageUrl': PAGE,
            },
            open_menu=lambda extension: head.open_action_context_menu(self, extension, 'page'),
            close_menu=self.close_menu,
            **kwargs)

    def test_03_show_hide_pageAction(self):
        self.page_action_task()

    def test_04_show_hide_pageAction_v3(self):
        self.page_action_task(manifest_version=3, id='page-action@mochitest',
                              menu_create_params={'id': 'page_action_item'})

    def test_05_show_hide_browserAction(self):
        self.show_hide_event(
            menu_create_params={
                'title': 'browserAction item',
                'contexts': ['browser_action'],
            },
            expected_shown_event={
                'contexts': ['browser_action', 'all'],
                'editable': False,
            },
            expected_shown_event_with_permissions={
                'contexts': ['browser_action', 'all'],
                'editable': False,
                'pageUrl': PAGE,
            },
            open_menu=lambda extension: head.open_action_context_menu(self, extension, 'browser'),
            close_menu=self.close_menu)

    def test_06_show_hide_browserAction_v3(self):
        self.show_hide_event(
            manifest_version=3,
            id='browser-action@mochitest',
            menu_create_params={
                'id': 'action_item',
                'title': 'Action item',
                'contexts': ['action'],
            },
            expected_shown_event={
                'contexts': ['action', 'all'],
                'editable': False,
            },
            expected_shown_event_with_permissions={
                'contexts': ['action', 'all'],
                'editable': False,
                'pageUrl': PAGE,
            },
            open_menu=lambda extension: head.open_action_context_menu(self, extension, 'browser'),
            close_menu=self.close_menu)

    def popup_task(self, **kwargs):
        popups = []

        def expected(extension):
            return {
                'contexts': ['page', 'all'],
                'viewType': 'popup',
                'frameId': 0,
                'editable': False,
                'pageUrl': f'chrome-extension://{extension.id}/popup.html',
                'targetElementId': EXPECT_TARGET_ELEMENT,
            }

        def open_menu(extension):
            popups.append(self.browser.open_popup(extension.id))
            head.open_context_menu_in_sidebar(self, popups[-1])

        def close_menu(extension):
            head.close_extension_context_menu(self)
            self.browser.close_target(popups.pop())

        self.show_hide_event(
            expected_shown_event=expected,
            expected_shown_event_with_permissions=expected,
            open_menu=open_menu,
            close_menu=close_menu,
            **kwargs)

    def test_07_show_hide_browserAction_popup(self):
        self.popup_task(menu_create_params={
            'title': 'browserAction popup - TEST_EXPECT_NO_TAB',
            'contexts': ['all', 'browser_action'],
        })

    def test_08_show_hide_browserAction_popup_v3(self):
        self.popup_task(
            manifest_version=3,
            id='browser-action-popup@mochitest',
            menu_create_params={
                'id': 'action_popup',
                'title': 'Action popup - TEST_EXPECT_NO_TAB',
                'contexts': ['all', 'action'],
            })

    def show_hide_tab_menu(self, open_tab_context_menu, close_tab_context_menu):
        """testShowHideTabMenu()."""
        self.show_hide_event(
            # To verify that the event matches the contextmenu target, switch to
            # an unrelated tab before opening a contextmenu on the desired tab.
            force_tab_to_background=True,
            menu_create_params={
                'title': 'tab menu item',
                'contexts': ['tab'],
            },
            expected_shown_event={
                'contexts': ['tab'],
                'editable': False,
            },
            expected_shown_event_with_permissions={
                'contexts': ['tab'],
                'editable': False,
                'pageUrl': PAGE,
            },
            open_menu=lambda extension: open_tab_context_menu(self.test_tab),
            close_menu=lambda extension: close_tab_context_menu())

    def test_09_show_hide_tab(self):
        def open_tab_context_menu(context_tab):
            # The test tab is the last one in the tab strip.
            head.open_tab_context_menu(self)

        self.show_hide_tab_menu(open_tab_context_menu, lambda: head.close_context_menu(self))

    # Checks that right-clicking on a tab in the all-tabs panel
    # results in an event that is associated with the expected tab.
    def test_10_show_hide_tab_via_tab_panel(self):
        def open_tab_context_menu(context_tab):
            raise AssertionError("this browser's list of all tabs has no tab menu")

        self.show_hide_tab_menu(open_tab_context_menu, lambda: head.close_context_menu(self))

    def test_11_show_hide_tools_menu(self):
        self.show_hide_event(
            menu_create_params={
                'title': 'menu item',
                'contexts': ['tools_menu'],
            },
            expected_shown_event={
                'contexts': ['tools_menu'],
                'editable': False,
            },
            expected_shown_event_with_permissions={
                'contexts': ['tools_menu'],
                'editable': False,
                'pageUrl': PAGE,
            },
            open_menu=lambda extension: head.open_tools_menu(self),
            close_menu=self.close_menu)

    def test_12_show_hide_page(self):
        self.show_hide_event(
            menu_create_params={
                'title': 'page menu item',
                'contexts': ['page'],
            },
            expected_shown_event={
                'contexts': ['page', 'all'],
                'viewType': 'tab',
                'editable': False,
                'frameId': 0,
            },
            expected_shown_event_with_permissions={
                'contexts': ['page', 'all'],
                'viewType': 'tab',
                'editable': False,
                'pageUrl': PAGE,
                'frameId': 0,
                'targetElementId': EXPECT_TARGET_ELEMENT,
            },
            open_menu=self.open_page_menu('body'),
            close_menu=self.close_menu)

    def test_13_show_hide_frame(self):
        # frame info will be determined before opening the menu.
        frame = {}

        def expected(with_permissions):
            def info(extension):
                result = {
                    'contexts': ['frame', 'all'],
                    'viewType': 'tab',
                    'editable': False,
                    'frameId': frame['id'],
                }
                if with_permissions:
                    result.update({
                        'pageUrl': PAGE,
                        'frameUrl': PAGE_BASE + 'context_frame.html',
                        'targetElementId': EXPECT_TARGET_ELEMENT,
                    })
                return result
            return info

        def open_menu(extension):
            frame['id'] = self.frame_id()
            head.open_context_menu(self, self.test_tab, 'body', frame_index=0)

        self.show_hide_event(
            menu_create_params={
                'title': 'subframe menu item',
                'contexts': ['frame'],
            },
            expected_shown_event=expected(False),
            expected_shown_event_with_permissions=expected(True),
            open_menu=open_menu,
            close_menu=self.close_menu)

    def test_14_show_hide_password(self):
        self.show_hide_event(
            menu_create_params={
                'title': 'password item',
                'contexts': ['password'],
            },
            expected_shown_event={
                'contexts': ['editable', 'password', 'all'],
                'viewType': 'tab',
                'editable': True,
                'frameId': 0,
            },
            expected_shown_event_with_permissions={
                'contexts': ['editable', 'password', 'all'],
                'viewType': 'tab',
                'editable': True,
                'frameId': 0,
                'pageUrl': PAGE,
                'targetElementId': EXPECT_TARGET_ELEMENT,
            },
            open_menu=self.open_page_menu('#password'),
            close_menu=self.close_menu)

    def test_15_show_hide_link(self):
        self.show_hide_event(
            menu_create_params={
                'title': 'link item',
                'contexts': ['link'],
            },
            expected_shown_event={
                'contexts': ['link', 'all'],
                'viewType': 'tab',
                'editable': False,
                'frameId': 0,
            },
            expected_shown_event_with_permissions={
                'contexts': ['link', 'all'],
                'viewType': 'tab',
                'editable': False,
                'frameId': 0,
                'linkText': 'Some link',
                'linkUrl': PAGE_BASE + 'some-link',
                'pageUrl': PAGE,
                'targetElementId': EXPECT_TARGET_ELEMENT,
            },
            open_menu=self.open_page_menu('#link1'),
            close_menu=self.close_menu)

    def test_16_show_hide_image_link(self):
        self.show_hide_event(
            menu_create_params={
                'title': 'image item',
                'contexts': ['image'],
            },
            expected_shown_event={
                'contexts': ['image', 'link', 'all'],
                'viewType': 'tab',
                'mediaType': 'image',
                'editable': False,
                'frameId': 0,
            },
            expected_shown_event_with_permissions={
                'contexts': ['image', 'link', 'all'],
                'viewType': 'tab',
                'mediaType': 'image',
                'editable': False,
                'frameId': 0,
                # Apparently, when a link has no content, its href is used as linkText.
                'linkText': PAGE_BASE + 'image-around-some-link',
                'linkUrl': PAGE_BASE + 'image-around-some-link',
                'srcUrl': PAGE_BASE + 'ctxmenu-image.png',
                'pageUrl': PAGE,
                'targetElementId': EXPECT_TARGET_ELEMENT,
            },
            open_menu=self.open_page_menu('#img-wrapped-in-link'),
            close_menu=self.close_menu)

    def test_17_show_hide_editable_selection(self):
        selection = {}

        def expected(with_permissions):
            def info(extension):
                result = {
                    'contexts': ['editable', 'selection', 'all'],
                    'viewType': 'tab',
                    'editable': True,
                    'frameId': 0,
                }
                if with_permissions:
                    result.update({
                        'pageUrl': PAGE,
                        'selectionText': selection['text'],
                        'targetElementId': EXPECT_TARGET_ELEMENT,
                    })
                return result
            return info

        def open_menu(extension):
            # Select lots of text in the test page before opening the menu.
            selection['text'] = self.test_tab.eval('''(() => {
              let node = document.getElementById("editabletext");
              node.scrollIntoView();
              node.select();
              node.focus();
              return node.value;
            })()''')
            head.open_context_menu(self, self.test_tab, '#editabletext')

        self.show_hide_event(
            menu_create_params={
                'title': 'editable item',
                'contexts': ['editable'],
            },
            expected_shown_event=expected(False),
            expected_shown_event_with_permissions=expected(True),
            open_menu=open_menu,
            close_menu=self.close_menu)

    def media_task(self, kind, url):
        """test_show_hide_video() and test_show_hide_audio()."""
        def open_menu(extension):
            self.test_tab.eval(f'''(() => {{
              let media = document.createElement({json.dumps(kind)});
              media.controls = true;
              media.src = {json.dumps(url)};
              document.body.appendChild(media);
              media.scrollIntoView();
              media.focus();
            }})()''')
            head.open_context_menu(self, self.test_tab, kind)

        self.show_hide_event(
            menu_create_params={
                'title': f'{kind} item',
                'contexts': [kind],
            },
            expected_shown_event={
                'contexts': [kind, 'all'],
                'viewType': 'tab',
                'mediaType': kind,
                'editable': False,
                'frameId': 0,
            },
            expected_shown_event_with_permissions={
                'contexts': [kind, 'all'],
                'viewType': 'tab',
                'mediaType': kind,
                'editable': False,
                'frameId': 0,
                'srcUrl': url,
                'pageUrl': PAGE,
                'targetElementId': EXPECT_TARGET_ELEMENT,
            },
            open_menu=open_menu,
            close_menu=self.close_menu)

    def test_18_show_hide_video(self):
        self.media_task('video', 'data:video/webm,xxx')

    def test_19_show_hide_audio(self):
        self.media_task('audio', 'data:audio/ogg,xxx')
