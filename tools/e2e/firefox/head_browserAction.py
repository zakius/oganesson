"""Firefox's browser/components/extensions/test/browser/head_browserAction.js:
testPopupSize(), which the ports of Firefox's browserAction popup resize
tests share.

The add-on's popup is Firefox's, as it is. Its button in Firefox's
navigation bar is the add-on pinned to the toolbar here, and CustomizableUI's
move of the button to the add-ons panel is the add-on unpinned into the
Extensions menu (head.pin_to_toolbar()). openBrowserActionPanel() is a real
click on the toolbar button, or on the add-on's row in the Extensions menu
that the window's Extensions button opens; the popup that opens is a bubble
either way (Chromium's ExtensionPopup, head_pageAction.popup_view()), as
Firefox's popup from its add-ons panel is a panel of its own. So the popup
is never Firefox's fixed-width subview of the menu panel (isFixedWidth is
false), and the panel's `side` attribute, the side of its arrow, is where
the bubble is: "top" when it opens below the window's Extensions button,
"bottom" when above. The panel's and the popup browser's sizes and places
are the bubble's and its web view's, on the screen (UI DevTools). Firefox's
waitUntilValue() polls as Firefox's does.

Left out: the panel's `animate` attribute, which only turns off the
animation of Firefox's panel; the bubble here has none to wait for.
"""

import time

from firefox import head, head_pageAction
from harness import Page, wait_for


def wait_until_value(get_value, is_completed, message, delay, times=1):
    """waitUntilValue(): reads `get_value()` twice, `delay` seconds apart,
    until `is_completed(old, new)` holds `times` times in a row."""
    count = 0

    def done():
        nonlocal count
        old = get_value()
        time.sleep(delay)
        new = get_value()
        count = count + 1 if is_completed(old, new) else 0
        return count == times

    # TestUtils.waitForCondition(): 50 tries, 100 ms apart.
    wait_for(done, timeout=50 * (0.1 + 2 * delay), interval=0.1, what=message)


def open_browser_action_panel(test, extension, pinned):
    """openBrowserActionPanel(): a click on the add-on's button in the
    newest window (the test's window), on the toolbar when it is `pinned`,
    else in the Extensions menu; its popup page, once it has loaded."""
    if pinned:
        test.browser.click_view(head.action_button(test))
    else:
        test.browser.click_view(head.window_view(test, 'ExtensionsToolbarButton'))
        test.browser.click_view(test.browser.wait_view('ExtensionsMenuButton',
                                                       Text='Generated extension'))
    return head_pageAction.await_extension_panel(test, extension)


def close_browser_action(test, extension):
    """closeBrowserAction(): the add-on's popup closes."""
    for target in head_pageAction.popup_targets(test, extension):
        test.browser.close_target(Page(target))
    head_pageAction.wait_popup_hidden(test, extension)


def window_screen(test):
    """The screen of the test's window, `browserWin.screen`: read in a tab,
    as all windows here are on one screen."""
    target = next(t for t in test.browser.targets() if t['type'] == 'page')
    page = Page(target)
    try:
        return page.eval('({height: screen.height, availTop: screen.availTop, '
                         'availLeft: screen.availLeft, availWidth: screen.availWidth, '
                         'availHeight: screen.availHeight})', gesture=False)
    finally:
        page.close()


def panel_rect(test):
    """The popup panel's rectangle on the screen: the bubble's."""
    bounds = head_pageAction.popup_view(test).bounds
    return {'top': bounds['y'], 'bottom': bounds['y'] + bounds['height']}


def panel_side(test):
    """The panel's `side` attribute: "top" when the bubble is below the
    newest window's Extensions button, "bottom" when it is above."""
    anchor = head.window_view(test, 'ExtensionsToolbarButton')
    return 'top' if panel_rect(test)['top'] >= anchor.center[1] else 'bottom'


def test_popup_size(test, standards_mode, arrow_side='top'):
    """testPopupSize(), in the newest window: the test's `browserWin`."""
    doc_type = '<!DOCTYPE html>' if standards_mode else ''
    screen = window_screen(test)

    extension = test.load_extension(
        manifest={
            'browser_action': {
                'default_popup': 'popup.html',
                'default_area': 'navbar',
                'browser_style': False,
            },
        },

        files={
            'popup.html': f'''{doc_type}
        <html>
          <head>
            <meta charset="utf-8">
            <style type="text/css">
              body > span {{
                display: inline-block;
                width: 10px;
                height: 150px;
                border: 2px solid black;
              }}
              .big > span {{
                width: 300px;
                height: 100px;
              }}
              .bigger > span {{
                width: 150px;
                height: 150px;
              }}
              .huge > span {{
                height: {2 * screen['height']}px;
              }}
            </style>
          </head>
          <body>
            <span></span>
            <span></span>
            <span></span>
            <span></span>
          </body>
        </html>''',
        })

    extension.startup()

    if arrow_side == 'top':
        # Test the standalone panel for a toolbar button.
        browser = open_browser_action_panel(test, extension, pinned=True)

        dims = head_pageAction.content_dimensions(test, browser)

        test.is_(dims['isStandards'], standards_mode, 'Document has the expected compat mode')

        inner_width, inner_height = dims['window']['innerWidth'], dims['window']['innerHeight']

        dims = head_pageAction.alter_content(test, browser, '''() => {
      content.document.body.classList.add("bigger");
    }''')

        win = dims['window']
        test.check(abs(win['innerHeight'] - inner_height) <= 1,
                   f"Window height should not change ({win['innerHeight']} ~= {inner_height})")
        test.check(win['innerWidth'] > inner_width,
                   f"Window width should increase ({win['innerWidth']} > {inner_width})")

        dims = head_pageAction.alter_content(test, browser, '''() => {
      content.document.body.classList.remove("bigger");
    }''')

        win = dims['window']

        # The getContentSize calculation is not always reliable to single-pixel
        # precision.
        test.check(abs(win['innerHeight'] - inner_height) <= 1,
                   'Window height should return to approximately its original value '
                   f"({win['innerHeight']} ~= {inner_height})")
        test.check(abs(win['innerWidth'] - inner_width) <= 1,
                   'Window width should return to approximately its original value '
                   f"({win['innerWidth']} ~= {inner_width})")

        close_browser_action(test, extension)

    # Test the PanelUI panel for a menu panel button.
    head.pin_to_toolbar(test, extension, False)

    browser = open_browser_action_panel(test, extension, pinned=False)

    # Wait long enough to make sure the initial popup positioning has been completed (
    # by waiting until the value stays the same for 20 times in a row).
    wait_until_value(
        get_value=lambda: panel_rect(test)['top'],
        is_completed=lambda old_val, new_val: old_val == new_val,
        times=20,
        message='Wait the popup opening to be completed',
        delay=0.5,
    )

    orig_panel_rect = panel_rect(test)

    # Check that the panel is still positioned as expected.
    def check_panel_position():
        test.is_(panel_side(test), arrow_side, 'Panel arrow is positioned as expected')

        rect = panel_rect(test)
        if arrow_side == 'top':
            test.is_(rect['top'], orig_panel_rect['top'], 'Panel has not moved downwards')
            test.check(rect['bottom'] >= orig_panel_rect['bottom'],
                       'Panel has not shrunk from original size '
                       f"({rect['bottom']} >= {orig_panel_rect['bottom']})")

            screen_bottom = screen['availTop'] + screen['availHeight']
            test.check(rect['bottom'] <= screen_bottom,
                       'Bottom of popup should be on-screen. '
                       f"({rect['bottom']} <= {screen_bottom})")
        else:
            test.is_(rect['bottom'], orig_panel_rect['bottom'], 'Panel has not moved upwards')
            test.check(rect['top'] <= orig_panel_rect['top'],
                       'Panel has not shrunk from original size '
                       f"({rect['top']} <= {orig_panel_rect['top']})")

            test.check(rect['top'] >= screen['availTop'],
                       'Top of popup should be on-screen. '
                       f"({rect['top']} >= {screen['availTop']})")

    # Wait long enough to make sure the initial resize debouncing timer has
    # expired.
    wait_until_value(
        get_value=lambda: head_pageAction.content_dimensions(test, browser),
        is_completed=lambda old_dims, new_dims: (
            old_dims['window']['innerWidth'] == new_dims['window']['innerWidth']
            and old_dims['window']['innerHeight'] == new_dims['window']['innerHeight']),
        message='Wait the popup resize to be completed',
        delay=0.5,
    )

    dims = head_pageAction.content_dimensions(test, browser)

    test.is_(dims['isStandards'], standards_mode, 'Document has the expected compat mode')

    # If the browser's preferred height is smaller than the initial height of the
    # panel, then it will still take up the full available vertical space. Even
    # so, we need to check that we've gotten the preferred height calculation
    # correct, so check that explicitly.
    def get_height():
        return head_pageAction.popup_web_view(test).bounds['height']

    inner_width, inner_height = dims['window']['innerWidth'], dims['window']['innerHeight']
    height = get_height()

    set_class = '''className => {
    content.document.body.className = className;
  }'''

    # Increase body children's width. Expect them to wrap, and the frame to
    # grow vertically rather than widen.

    dims = head_pageAction.alter_content(test, browser, set_class, 'big')
    win = dims['window']

    test.check(get_height() > height,
               f'Browser height should increase ({get_height()} > {height})')

    # Firefox's fixed-width subview, whose width doesn't change and which
    # has a step of its own, isn't there (isFixedWidth is false).
    test.check(win['innerWidth'] >= inner_width,
               f"Window width should increase ({win['innerWidth']} >= {inner_width})")
    test.check(win['innerHeight'] >= inner_height,
               f"Window height should increase ({win['innerHeight']} >= {inner_height})")
    test.check(win['scrollMaxY'] <= 1, 'Document should not be vertically scrollable')

    check_panel_position()

    # Increase body height beyond the height of the screen. Expect the panel
    # to grow to accommodate, but not larger than the height of the screen.

    dims = head_pageAction.alter_content(test, browser, set_class, 'huge')
    win = dims['window']

    test.check(get_height() > height,
               f'Browser height should increase ({get_height()} > {height})')

    test.is_(win['innerWidth'], inner_width, 'Window width should not change')
    test.check(win['innerHeight'] > inner_height,
               f"Window height should increase ({win['innerHeight']} > {inner_height})")
    # Commented out check for the window height here which mysteriously breaks
    # on infra but not locally. bug 1396843 covers re-enabling this.
    test.check(win['scrollMaxY'] > 0,
               f"Document should be vertically scrollable ({win['scrollMaxY']} > 0)")

    check_panel_position()

    # Restore original styling. Expect original dimensions.
    dims = head_pageAction.alter_content(test, browser, set_class, '')
    win = dims['window']

    test.is_(get_height(), height, 'Browser height should return to its original value')

    test.is_(win['innerWidth'], inner_width, 'Window width should not change')
    test.is_(win['innerHeight'], inner_height, 'Window height should return to its original value')
    test.check(win['scrollMaxY'] <= 1, 'Document should not be vertically scrollable')

    check_panel_position()

    close_browser_action(test, extension)

    extension.unload()
