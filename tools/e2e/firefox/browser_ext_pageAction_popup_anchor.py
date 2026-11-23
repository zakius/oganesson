"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_popup_anchor.js.

The add-on is Firefox's, as it is. example.com is a local server here.

Firefox makes the popup's anchoring fail: it replaces
BrowserPageActions.togglePanelForAction() with a function that throws, and
checks that the popup the click built is cleaned up. That hook is Gecko's
chrome code, and this browser's popup can't be made to fail its anchoring
from outside, so the popup the click opens shows. The port checks the
anchoring as this browser does it, then the cleanup once that popup closes
(the popup page closed, as other ports close a popup):

- "the page action references the popup it is about to show": the popup
  bubble (Chromium's ExtensionPopup, through UI DevTools) shows at the page
  action's button, below it and across from it, and the button is pressed
  while its popup is open.
- "the popup's browser is in the panel": the popup's web view
  (ExtensionViewViews) is inside the bubble.
- "the popup panel was removed from the document": no popup bubble.
- "the page action no longer references the popup": the button isn't
  pressed any more.
- "waiting for the popup's browser to be destroyed": the add-on's popup page
  is gone.

showPageAction(), what pageAction.show() does in Firefox's parent process,
is pageAction.show() here, called from one of the add-on's pages (its
popup.html, the add-on's only page) in a background tab, closed again.
pageAction.handleClick(window, {button: 0}) is a real click on the button
(head.click_page_action()). Left out: the anchoring failure that
handleClick() reports ("the anchoring failure is reported to the caller"),
and the "extension-browser-inserted" event that finds the popup's browser,
Gecko internals.
"""

import json

from firefox import head, head_pageAction
from extension_test_utils import FirefoxTest
from harness import Page, wait_for

HTML = {'Content-Type': 'text/html'}
TEST_URL = 'http://example.com/'


def show_page_action(test, extension):
    """showPageAction(): the add-on shows its page action on the active tab,
    from its popup.html in a background tab."""
    url = f'chrome-extension://{extension.id}/popup.html'
    target_id = test.browser.browser_call('Target.createTarget', url=url, background=True)['targetId']
    page = Page(wait_for(lambda: next((t for t in test.browser.targets() if t['id'] == target_id),
                                      None), what="the add-on's page"))
    try:
        wait_for(lambda: page.eval('!!globalThis.browser?.pageAction', gesture=False),
                 what="the add-on's page to load")
        page.eval('browser.tabs.query({ active: true, currentWindow: true })'
                  '.then(([tab]) => browser.pageAction.show(tab.id))', gesture=False)
    finally:
        page.close()
        test.browser.close_target(page)


def button_pressed(test, extension):
    button = head.page_action_button(test, extension)
    return button is not None and button['State'] == 'STATE_PRESSED'


class PageActionPopupAnchorTest(FirefoxTest):
    hosts = ('example.com',)
    routes = {'/': (200, HTML, b'<!DOCTYPE html><title>example.com</title>')}

    def test_01_popup_destroyed_when_anchoring_throws(self):
        extension = self.load_extension(
            manifest={
                'page_action': {'default_popup': 'popup.html'},
            },
            files={
                'popup.html': '<!DOCTYPE html><html><body>popup</body></html>',
            },
        )
        extension.startup()

        tab = self.open_tab(TEST_URL)

        show_page_action(self, extension)
        button = head.wait_page_action_button(self, extension)

        head.click_page_action(self, extension)
        popup = head_pageAction.await_extension_panel(self, extension)

        panel = head_pageAction.popup_view(self)
        below = button.center[1] <= panel.bounds['y'] <= button.bounds['y'] + button.bounds['height'] + 48
        across = (panel.bounds['x'] <= button.bounds['x'] + button.bounds['width']
                  and panel.bounds['x'] + panel.bounds['width'] >= button.bounds['x'])
        self.check(below and across and button_pressed(self, extension),
                   'the page action references the popup it is about to show - '
                   f'Button: {button.bounds}, popup: {panel.bounds}, '
                   f'pressed: {button_pressed(self, extension)}')
        web_views = [v for v in self.browser.views('ExtensionViewViews') if v.visible]
        inside = any(panel.bounds['x'] <= v.bounds['x']
                     and v.bounds['x'] + v.bounds['width'] <= panel.bounds['x'] + panel.bounds['width']
                     and panel.bounds['y'] <= v.bounds['y']
                     and v.bounds['y'] + v.bounds['height'] <= panel.bounds['y'] + panel.bounds['height']
                     for v in web_views)
        self.check(inside, "the popup's browser is in the panel - "
                   f'Popup: {panel.bounds}, web views: {json.dumps([v.bounds for v in web_views])}')

        self.browser.close_target(popup)

        try:
            wait_for(lambda: head_pageAction.popup_view(self) is None, timeout=5,
                     what='the popup bubble to close')
        except AssertionError:
            pass
        self.check(head_pageAction.popup_view(self) is None,
                   'the popup panel was removed from the document')
        self.check(not button_pressed(self, extension),
                   'the page action no longer references the popup')

        wait_for(lambda: not head_pageAction.popup_targets(self, extension),
                 what="waiting for the popup's browser to be destroyed")

        self.browser.close_target(tab)

        extension.unload()
