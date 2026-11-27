"""Firefox's browser/components/extensions/test/browser/head.js: the helpers
that its browser tests share, and the test pages they load from mochitest's
server (http://mochi.test:8888/browser/browser/components/extensions/test/browser/).
Only what a port runs is here.

A context menu is the browser's own, opened with a real right click and read
through UI DevTools (harness.Browser.menus()). Firefox's menu is a DOM tree
that a test searches with getElementsByAttribute(); here a Menu holds the
items that it shows, top to bottom, and the test asks it for them by label.
Where Firefox gives an add-on with more than one item a submenu of its own
("top-level-menu"), this browser does too, under the add-on's name.
"""

import base64
import json
import subprocess

from extension_test_utils import JS, FirefoxTest
from harness import DEVELOPER_MODE, Page, wait_for
from test_google_lens import png

DIR = '/browser/browser/components/extensions/test/browser/'
BASE = f'http://mochi.test:8888{DIR}'

# Firefox's context.html and the frame in it, context_frame.html.
CONTEXT_HTML = b'''<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
  </head>
  <body>
  just some text 12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890
  <img src="ctxmenu-image.png" id="img1">

  <p>
    <a href="some-link" id="link1">Some link</a>
  </p>

  <p>
    <a href="image-around-some-link">
      <img src="ctxmenu-image.png" id="img-wrapped-in-link">
    </a>
  </p>

  <p>
    <input type="text" id="edit-me"><br>
    <input id="readonly-text" type="text" readonly >
    <input id="call-me-maybe" type="tel" value="0123456789">
    <input id="number-input" type="number" value="123456789"><br>
    <input type="password" id="password">
    <input id="noneditablepassword" type="password" readonly >
  </p>
  <iframe id="frame" src="context_frame.html"></iframe>
  <p id="longtext">Sed ut perspiciatis unde omnis iste natus error sit
  voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque
  ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta
  sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut
  odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem
  sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit
  amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora
  incidunt ut labore et dolore magnam aliquam quaerat voluptatem. Ut enim ad
  minima veniam, quis nostrum exercitationem ullam corporis suscipit
  laboriosam, nisi ut aliquid ex ea commodi consequatur? Quis autem vel eum
  iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae
  consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur?</p>

  <input id="editabletext" type="text" value="At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident, similique sunt in culpa qui officia deserunt mollitia animi, id est laborum et dolorum fuga. Et harum quidem rerum facilis est et expedita distinctio. Nam libero tempore, cum soluta nobis est eligendi optio cumque nihil impedit quo minus id quod maxime placeat facere possimus, omnis voluptas assumenda est, omnis dolor repellendus. Temporibus autem quibusdam et aut officiis debitis aut rerum necessitatibus saepe eveniet ut et voluptates repudiandae sint et molestiae non recusandae. Itaque earum rerum hic tenetur a sapiente delectus, ut aut reiciendis voluptatibus maiores alias consequatur aut perferendis doloribus asperiores repellat." />
  </body>
</html>
'''

CONTEXT_FRAME_HTML = b'''<html>
  <head>
    <meta charset="utf-8">
  </head>
  <body>
  Just some text
  </body>
</html>
'''

CONTEXT_WITH_REDIRECT_HTML = b'''<!DOCTYPE html>
<meta charset="utf-8">

<img id="img_that_redirects" src="redirect_to.sjs?ctxmenu-image.png">
'''

# The test pages for a FirefoxTest's `routes`, with `hosts = ('mochi.test',)`.
# redirect_to.sjs sends the browser to its query string, here always
# ctxmenu-image.png, a 100 x 100 image as Firefox's is.
ROUTES = {
    f'{DIR}context.html': (200, {'Content-Type': 'text/html'}, CONTEXT_HTML),
    f'{DIR}context_frame.html': (200, {'Content-Type': 'text/html'}, CONTEXT_FRAME_HTML),
    f'{DIR}context_with_redirect.html': (200, {'Content-Type': 'text/html'},
                                         CONTEXT_WITH_REDIRECT_HTML),
    f'{DIR}ctxmenu-image.png': (200, {'Content-Type': 'image/png'}, png(100)),
    f'{DIR}redirect_to.sjs': (302, {'Location': 'ctxmenu-image.png'}, b''),
}

# Firefox's EventUtils modifiers, as xdotool's keys.
MODIFIERS = {'shiftKey': 'shift', 'ctrlKey': 'ctrl', 'altKey': 'alt', 'metaKey': 'super'}


class ContextMenuTest(FirefoxTest):
    """A test file that opens context menus on head.py's test pages. A menu
    that a failed test leaves open closes when the next test starts, whose
    right click it would take; until then the failure's screenshot shows it."""
    hosts = ('mochi.test',)
    routes = ROUTES

    def setUp(self):
        super().setUp()
        close_context_menu(self)


class Menu:
    """An open menu's items (MenuItemViews), as they were when it opened, and
    its groups of items between separators (harness.Browser.menus())."""

    def __init__(self, test, items, groups=None):
        self.test = test
        self.items = items
        self.groups = groups or [items]

    def ends_group(self, item):
        """A separator follows `item`: it is the last of its group."""
        return any(group[-1] is item for group in self.groups[:-1])

    def by_label(self, label):
        """getElementsByAttribute("label", label): the items with that label."""
        return [item for item in self.items if label_of(item) == label]

    def checkable(self):
        """getElementsByAttribute("type", "checkbox") or ("type", "radio"):
        the items with a check mark or a radio button. The menu doesn't say
        which of the two an item is, so a port reads them together. Only in
        an add-on's submenu: in the context menu itself, an add-on's item has
        the add-on's icon where the check mark goes."""
        return [item for item in self.items if check_image(self.test, item)]

    def is_checked(self, item):
        """hasAttribute("checked"): the item shows a check mark or a selected
        radio button. A checkbox's mark shows only when it is checked, a radio
        button's always; a selected one has a dot in its middle, so the
        image's middle differs from its corner on the screen."""
        image = check_image(self.test, item)
        if not image or not image.visible:
            return False
        x, y = image.center
        corner = image.bounds['x'], image.bounds['y']
        return self.test.browser.pixel(x, y) != self.test.browser.pixel(*corner)


def has_submenu(test, item):
    """tagName == "menu": the item opens a submenu, so it shows the submenu's
    arrow, an image at its end."""
    box = item.bounds
    for image in test.browser.views('ImageView'):
        x, y = image.center
        inside = box['x'] <= x < box['x'] + box['width'] and box['y'] <= y < box['y'] + box['height']
        if inside and image.visible and box['x'] + box['width'] - image.bounds['x'] < 40:
            return True
    return False


def access_key(item):
    """accessKey: the character after the title's first `&` that isn't
    `&&`, which the menu underlines, or None."""
    title = item['Title'].replace('&&', '')
    index = title.find('&')
    if index < 0 or index + 1 >= len(title):
        return None
    return title[index + 1]


def label_of(item):
    """The item's label as Firefox has it: the menu's title without the
    mnemonic's `&`, and `&&` as `&`."""
    return item['Title'].replace('&&', '\0').replace('&', '').replace('\0', '&')


def check_image(test, item):
    """The image at the start of `item` that a checkbox or radio item has
    (MenuItemView's radio_check_image_view_), shown or not, or None. An
    item's icon is there too."""
    box = item.bounds
    for image in test.browser.views('ImageView'):
        x, y = image.center
        inside = box['x'] <= x < box['x'] + box['width'] and box['y'] <= y < box['y'] + box['height']
        if inside and image.bounds['x'] - box['x'] < 40 and image.bounds['width']:
            return image
    return None


def open_menus(test):
    """The open menus once one is open (harness.Browser.menus())."""
    return wait_for(lambda: test.browser.menus(), what='a menu to open')


# synthesizeMouseAtCenter()'s point in a page: the centre of the first
# match of a selector, in the page or in its frame number `frameIndex`, in
# the page's coordinates; (0, 0) when nothing matches, where Firefox clicks
# then.
POINT = '''((selector, frameIndex) => {
  let doc = document;
  let left = 0;
  let top = 0;
  if (frameIndex !== null) {
    const frame = window.frames[frameIndex].frameElement;
    const rect = frame.getBoundingClientRect();
    doc = frame.contentDocument;
    left = rect.left;
    top = rect.top;
  }
  const target = doc.querySelector(selector);
  if (!target) {
    return [0, 0];
  }
  const rect = target.getBoundingClientRect();
  return [left + rect.left + rect.width / 2, top + rect.top + rect.height / 2];
})'''


# The centre of an element, in the page's coordinates; (0, 0) for none.
ELEMENT_POINT = '''(target => {
  if (!target) {
    return [0, 0];
  }
  const rect = target.getBoundingClientRect();
  return [rect.left + rect.width / 2, rect.top + rect.height / 2];
})'''


def point(page, selector, frame_index=None):
    """The point of synthesizeMouseAtCenter(selector): `selector` is a CSS
    selector, or a function (JS) that runs in the page and returns the
    element, as Firefox's test may pass."""
    if isinstance(selector, JS):
        return page.eval(f'{ELEMENT_POINT}(({selector.source.strip()})())')
    return page.eval(f'{POINT}({json.dumps(selector)}, {json.dumps(frame_index)})')


def window_view(test, cls):
    """The visible view of class `cls` in the newest window: a test's
    window, as Firefox's `win`, is the one it opened last, which has the
    focus. Widget node ids grow as widgets are created."""
    def newest():
        views = [view for view in test.browser.views(cls) if view.visible]
        return max(views, key=lambda view: view.widget) if views else None
    return test.browser.wait_settled(newest, what=f'a visible {cls}')


def first_menu(test):
    """The menu that opens first, once it is open."""
    groups = open_menus(test)[0]
    return Menu(test, [item for group in groups for item in group], groups)


def open_context_menu(test, page, selector='#img1', frame_index=None):
    """openContextMenu(), or openContextMenuInFrame() with `frame_index`: a
    right click on `selector` (point()) in `page`, the active tab of the
    newest window, or in its frame; the context menu that opens."""
    contents = window_view(test, 'ContentsWebView')
    x, y = point(page, selector, frame_index)
    test.browser.xdotool('mousemove', str(contents.bounds['x'] + int(x)),
                         str(contents.bounds['y'] + int(y)), 'click', '3')
    return first_menu(test)


def open_tab_context_menu(test, index=-1):
    """openTabContextMenu(), or openChromeContextMenu("tabContextMenu",
    ".tabbrowser-tab") with `index` 0: a right click on the tab at `index` in
    the tab strip; the context menu that opens. The default, the last tab,
    is the selected one when the test has just opened it. The click waits
    for the tabs to stop moving: they slide into place as others close."""
    tabs = test.browser.wait_settled(
        lambda: sorted((view for view in test.browser.views('Tab') if view.visible),
                       key=lambda view: view.bounds['x']),
        what='the tab strip')
    test.browser.click_view(tabs[index], button=3)
    return first_menu(test)


def open_action_context_menu(test, extension, kind):
    """openActionContextMenu(extension, kind): a right click on the add-on's
    toolbar button (`kind` "browser"), or on its page action's button in the
    location bar ("page", wait_page_action_button()); the context menu that
    opens."""
    if kind == 'page':
        test.browser.click_view(wait_page_action_button(test, extension), button=3)
        return first_menu(test)
    test.browser.click_view(test.browser.toolbar_button(extension.id), button=3)
    return first_menu(test)


def open_tools_menu(test):
    """openToolsMenu(): this browser has no Tools menu, and an add-on's
    `tools_menu` items go in the app menu's More tools (zakius/oganesson#98):
    that submenu of the newest window, open."""
    test.browser.click_view(window_view(test, 'BrowserAppMenuButton'))
    menu = first_menu(test)
    return open_submenu(test, menu.by_label('More tools')[0])


def open_extensions_panel(test, timeout=15):
    """openExtensionsPanel(): Firefox's unified extensions panel is this
    browser's Extensions menu, which the toolbar's Extensions button opens."""
    test.browser.click_view(test.browser.wait_view('ExtensionsToolbarButton'))
    wait_for(lambda: any(view.visible for view in test.browser.views('ExtensionMenuItemView')),
             timeout=timeout, what='the Extensions menu')


def close_extensions_panel(test):
    """closeExtensionsPanel()."""
    def closed():
        if not any(view.visible for view in test.browser.views('ExtensionMenuItemView')):
            return True
        test.browser.key('Escape')
        return False
    wait_for(closed, interval=0.5, what='the Extensions menu to close')


def open_unified_extensions_context_menu(test, name='Generated extension'):
    """openUnifiedExtensionsContextMenu(): the context menu of the add-on
    called `name` in the open Extensions menu, which its row's More options
    button opens."""
    browser = test.browser
    label = browser.wait_view('ExtensionsMenuButton', Text=name)
    row = next(view for view in browser.views('ExtensionMenuItemView')
               if view.bounds['y'] <= label.center[1] < view.bounds['y'] + view.bounds['height'])
    button = next(view for view in browser.views('HoverButton', TooltipText='More options')
                  if row.bounds['y'] <= view.center[1] < row.bounds['y'] + row.bounds['height'])
    browser.click_view(button)
    return first_menu(test)


def extension_tab(test, extension, name):
    """The tab of the add-on's page `name`, which the add-on opened, once it
    has loaded (BrowserTestUtils.waitForNewTab())."""
    page = test.browser.page(f'chrome-extension://{extension.id}/{name}')
    wait_for(lambda: page.eval('document.readyState') == 'complete', what=f'{name} to load')
    return page


def open_whole_context_menu(test, page, selector='#img1', frame_index=None,
                            name='Generated extension'):
    """openContextMenu() as a test reads it with getElementsByAttribute(),
    which reaches into the closed submenu of an add-on with more than one
    item: the context menu's items, and those of the submenu of the add-on
    called `name`, opened."""
    menu = open_context_menu(test, page, selector, frame_index)
    top = menu.by_label(name)
    if not top:
        return menu
    return Menu(test, menu.items + open_submenu(test, top[0]).items)


def open_context_menu_in_sidebar(test, page, selector='body'):
    """openContextMenuInSidebar(): a right click on `selector` in `page`,
    an add-on's page in the side panel, as DevTools' input, since the side
    panel isn't the tab's view; the context menu that opens. The same for
    openContextMenuInPopup(), with the add-on's popup (Browser.open_popup())."""
    x, y = point(page, selector)
    for kind in ('mousePressed', 'mouseReleased'):
        page.call('Input.dispatchMouseEvent', type=kind, x=x, y=y, button='right', clickCount=1)
    menus = open_menus(test)
    return Menu(test, [item for group in menus[0] for item in group])


def close_context_menu(test):
    """closeContextMenu(): closes the open menus without choosing an item."""
    def closed():
        if not test.browser.menus():
            return True
        test.browser.key('Escape')
        return False
    wait_for(closed, interval=0.5, what='the menu to close')


def open_extension_context_menu(test, page, selector='#img1', name='Generated extension'):
    """openExtensionContextMenu(): the context menu's submenu of the add-on
    called `name`, open, or None when the add-on's item is in the context
    menu itself (it has only one)."""
    menu = open_context_menu(test, page, selector)
    top = menu.by_label(name)
    if not top:
        return None
    return open_submenu(test, top[0])


def open_submenu(test, item):
    """item.menupopup, open: a click on `item`, in the last open menu, opens
    its submenu, the next menu."""
    depth = len(test.browser.menus())
    test.browser.click_view(item)

    def submenu():
        menus = test.browser.menus()
        return menus[depth] if len(menus) > depth else None
    found = wait_for(submenu, what=f"{label_of(item)}'s submenu")
    return Menu(test, [entry for group in found for entry in group], found)


def synthesize_mouse_at_center(test, item, button=0):
    """EventUtils.synthesizeMouseAtCenter(item, {button}): a click on `item`
    with Firefox's button number (0 left, 1 middle, 2 right)."""
    x, y = item.center
    test.browser.xdotool('mousemove', str(x), str(y), 'click', str(button + 1))


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


def focus_toolbar_view(test, view):
    """`view`, a button in the toolbar or the location bar, gets the keyboard
    focus as the user gives it: the toolbar's keyboard focus (Alt+Shift+T),
    then Tab until the button's focus ring shows."""
    test.browser.key('alt+shift+t')
    for _ in range(40):
        if has_focus(test, view):
            return
        test.browser.key('Tab')
    raise AssertionError(f"{view} doesn't take the keyboard focus")


def close_extension_context_menu(test, item=None, modifiers=None):
    """closeExtensionContextMenu(): a click on `item` with the keys of
    `modifiers` held (Firefox's {shiftKey: true, ...}) and its `button`
    (synthesize_mouse_at_center()), or no item to close the menu; either way
    the menus close."""
    if item is None:
        close_context_menu(test)
        return
    modifiers = dict(modifiers or {})
    button = modifiers.pop('button', 0)
    keys = [MODIFIERS[name] for name, held in modifiers.items() if held]
    browser = test.browser
    for key in keys:
        browser.xdotool('keydown', key)
    try:
        synthesize_mouse_at_center(test, item, button)
    finally:
        for key in reversed(keys):
            browser.xdotool('keyup', key)
    wait_for(lambda: not browser.menus(), what='the menu to close')


def open_new_browser_window(test):
    """BrowserTestUtils.openNewBrowserWindow() and focusWindow(): a new
    window with one blank tab, once it has the focus; its DevTools windowId."""
    browser = test.browser
    target = browser.browser_call('Target.createTarget', url='about:blank',
                                  newWindow=True)['targetId']
    page = Page(wait_for(lambda: next((t for t in browser.targets() if t['id'] == target), None),
                         what='the new window'))
    try:
        wait_for(lambda: page.eval('document.hasFocus()'), what='the new window to have the focus')
    finally:
        page.close()
    return browser.browser_call('Browser.getWindowForTarget', targetId=target)['windowId']


def open_private_window(test):
    """BrowserTestUtils.openNewBrowserWindow({private: true}): a new private
    window, as the user opens one (Ctrl+Shift+N); its tab, once it has
    loaded."""
    before = {target['id'] for target in test.browser.targets()}
    test.browser.key('ctrl+shift+n')
    page = Page(wait_for(lambda: next((target for target in test.browser.targets()
                                       if target['id'] not in before and target['type'] == 'page'),
                                      None), what='the private window'))
    wait_for(lambda: page.eval('document.readyState') == 'complete',
             what='the private window to load')
    return page


def window_of(test, page):
    """The DevTools windowId of `page`'s window."""
    return test.browser.browser_call('Browser.getWindowForTarget', targetId=page.id)['windowId']


def close_window(test, window_id):
    """BrowserTestUtils.closeWindow(): closes the window's tabs, and so the
    window."""
    browser = test.browser

    def tabs():
        found = []
        for target in browser.targets():
            if target['type'] != 'page':
                continue
            try:
                window = browser.browser_call('Browser.getWindowForTarget', targetId=target['id'])
            except RuntimeError:
                continue  # Closed meanwhile.
            if window['windowId'] == window_id:
                found.append(target)
        return found

    for target in tabs():
        browser.browser_call('Target.closeTarget', targetId=target['id'])
    wait_for(lambda: not tabs(), what='the window to close')


def toggle_bookmarks_toolbar(test, visible=True):
    """toggleBookmarksToolbar(): shows or hides the bookmark bar on every tab
    (Ctrl+Shift+B), and waits until it has. The pref bookmark_bar.visibility_state
    is 0 for every tab, 1 (the default) for the new tab page only and 2 for
    none; the key toggles between 0 and 2."""
    def on_all_tabs():
        prefs = test.browser.profile_prefs()
        return prefs.get('bookmark_bar', {}).get('visibility_state', {}).get('value', 1) == 0
    if on_all_tabs() != visible:
        test.browser.key('ctrl+shift+b')
    wait_for(lambda: on_all_tabs() == visible, interval=0.5,
             what=f'the bookmark bar to be {"shown" if visible else "hidden"} on every tab')
    if visible:
        wait_for(lambda: any(view.visible and view.bounds['height']
                             for view in test.browser.views('BookmarkBarView')),
                 what='the bookmark bar to show')


# The `prefs` of a port whose add-ons start without their buttons pinned, as
# Firefox puts a new add-on's button in the add-ons panel unless its manifest's
# `default_area` names a toolbar: this browser pins new extensions unless its
# setting says not to.
NOT_PINNED_BY_DEFAULT = {'extensions': {**DEVELOPER_MODE['extensions'], 'pinned_by_default': False}}


def pin_to_toolbar(test, extension, pinned):
    """pinToToolbar() of Firefox's action tests: CustomizableUI's move of the
    add-on's button to the navigation bar or to the add-ons panel is the
    add-on pinned to the toolbar or unpinned into the Extensions menu, as the
    user does on its page in chrome://extensions."""
    page = test.browser.new_tab('chrome://extensions')
    try:
        wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
        page.eval('chrome.developerPrivate.updateExtensionConfiguration('
                  f'{{extensionId: {json.dumps(extension.id)}, pinnedToToolbar: {json.dumps(pinned)}}})')
    finally:
        test.browser.close_target(page)


def open_chrome_context_menu(test, view):
    """openChromeContextMenu(): a right click on a view of the browser's own
    UI (`view`, from harness.Browser.views()); the context menu that opens."""
    test.browser.click_view(view, button=3)
    return first_menu(test)


def screen_pixels(test, x, y, width, height):
    """The screen's colours in a rectangle, as rows of (r, g, b)
    (ImageMagick's import)."""
    out = subprocess.run(['import', '-window', 'root', '-crop', f'{width}x{height}+{x}+{y}',
                          '-depth', '8', 'rgb:-'],
                         env=test.browser.env(), capture_output=True, check=True).stdout
    rows = []
    for row in range(height):
        start = row * width * 3
        rows.append([tuple(out[start + i * 3:start + i * 3 + 3]) for i in range(width)])
    return rows


def action_button(test):
    """The add-on's toolbar button in the newest window, as Firefox's tests
    read the widget of their add-on in their window (window_view()): the
    last one pinned, as the test's add-on is the newest, and this browser
    pins a new add-on's button."""
    def newest():
        views = [view for view in test.browser.views('ToolbarActionView') if view.visible]
        if not views:
            return None
        window = max(view.widget for view in views)
        return max((view for view in views if view.widget == window),
                   key=lambda view: view.bounds['x'])
    return test.browser.wait_settled(newest, what="the add-on's toolbar button")


def greyed(colour):
    """The grey that a disabled action's icon of `colour` shows: no
    saturation, and lightness shifted up a fifth (IconWithBadgeImageSource's
    HSL shift)."""
    lightness = (max(colour) + min(colour)) / 2
    return lightness + (255 - lightness) * 0.2


# Points on a toolbar button, 28 x 28 here (IconWithBadgeImageSource): the
# icon, 16 x 16 from (6, 6); a badge, 14 high along the bottom and at least
# 14 wide, right-aligned or centred, with the icon cleared 1 pixel around
# it; the badge's background above its text, which starts at row 18.
ICON_POINT = (9, 9)
BADGE_GAP_POINT = (20, 13)
BADGE_POINT = (20, 16)


def action_button_state(test, images):
    """What the add-on's toolbar button (action_button()) shows, where
    Firefox's tests read its widget's `tooltiptext`, `label`, `image`,
    `disabled` and `badge`: `title`, its tooltip; `icon`, the name of the
    image of `images` ({file name: (r, g, b)}, a PNG of that one colour) that
    it shows, or None; `enabled`, False when the icon is grey, as this
    browser shows a disabled action, whose button can still be clicked;
    `badge`, whether it shows a badge; and the badge's `badge_background`
    and `badge_text_color`, (r, g, b), its text's being the colour that
    differs most from its background. The badge's text is painted on the
    button and can't be read. The mouse moves off the button first: a
    hovered button is tinted."""
    test.browser.xdotool('mousemove', '650', '500')
    button = action_button(test)
    left, top = button.bounds['x'], button.bounds['y']
    # From 2 pixels above the button: the toolbar.
    rows = screen_pixels(test, left, top - 2, 28, 30)

    def at(x, y):
        return rows[y + 2][x]

    toolbar = rows[0][14]
    icon = at(*ICON_POINT)
    enabled = not icon[0] == icon[1] == icon[2]
    shown = None
    for name, colour in images.items():
        if enabled and icon == tuple(colour):
            shown = name
        if not enabled and abs(icon[0] - greyed(colour)) <= 2:
            shown = name
    badge = at(*BADGE_GAP_POINT) == toolbar and at(*BADGE_POINT) != toolbar
    background = None
    text = None
    if badge:
        background = at(*BADGE_POINT)
        # The badge's row, then 3 pixels in from its ends: its rounded
        # corners blend with the toolbar.
        left, top = BADGE_POINT
        while left > 0 and at(left - 1, top) == background:
            left -= 1
        right = BADGE_POINT[0]
        while right < 27 and at(right + 1, top) == background:
            right += 1

        def difference(pixel):
            return sum(abs(a - b) for a, b in zip(pixel, background))
        inside = [at(x, y) for y in range(top + 1, 28) for x in range(left + 3, right - 2)]
        text = max(inside, key=difference)
    return {'title': button['TooltipText'], 'icon': shown, 'enabled': enabled, 'badge': badge,
            'badge_background': background, 'badge_text_color': text}


# Firefox's imageBuffer: a 1 x 1 PNG.
IMAGE_BUFFER = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQImWNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg==')


def page_action_button(test, extension):
    """getPageActionButton(), or the element of the id that
    BrowserPageActions.urlbarButtonNodeIDForActionID() gives: the add-on's
    page action button in the location bar of the newest window (as
    window_view()), which shows where the page action is shown, or None.
    It is a FirefoxPageActionView with the add-on's ExtensionId. Chromium's
    toolbar button for a Manifest V2 add-on whose only action is a page
    action isn't it: that button stays in the toolbar on every tab, greyed
    out where the page action is hidden."""
    views = test.browser.views('FirefoxPageActionView', ExtensionId=extension.id)
    if not views:
        return None
    # Each window has the add-on's button, hidden where the page action is:
    # another window's shown button isn't this window's.
    newest = max(views, key=lambda view: view.widget)
    return newest if newest.visible else None


def wait_page_action_button(test, extension):
    """The add-on's page action button (page_action_button()), once it shows
    and stops moving: the location bar lays its items out anew as buttons
    come and go."""
    return test.browser.wait_settled(lambda: page_action_button(test, extension),
                                     what="the add-on's page action button")


def click_page_action(test, extension):
    """clickPageAction(): a real click on the add-on's page action button in
    the location bar."""
    test.browser.click_view(wait_page_action_button(test, extension))


def tab_location(page):
    """The tab's location as the browser has it (gBrowser's currentURI): its
    current history entry's URL."""
    history = page.call('Page.getNavigationHistory')
    return history['entries'][history['currentIndex']]['url']


def history_push_state(page, url):
    """historyPushState(): history.pushState() to `url` in the tab's page,
    once the browser has the tab's new location."""
    page.eval(f'history.pushState(null, null, {json.dumps(url)})')
    wait_for(lambda: tab_location(page) == url, what=f'the location {url}')


def active_tab_id(test, extension):
    """tabTracker.getId() of the selected tab: the tabs API's ID of the active
    tab of the last focused window, which the test asks the add-on's
    background for through DevTools."""
    page = test.browser.extension_background(extension.id)
    try:
        return page.eval('chrome.tabs.query({active: true, lastFocusedWindow: true})'
                         '.then(tabs => tabs[0].id)', gesture=False)
    finally:
        page.close()


def set_enabled(test, extension, enabled):
    """AddonManager's disable() and enable(): management.setEnabled() from
    chrome://extensions."""
    page = test.open_tab('chrome://extensions')
    try:
        wait_for(lambda: page.eval('!!chrome.management'), what='chrome://extensions')
        page.eval(f'chrome.management.setEnabled({json.dumps(extension.id)}, '
                  f'{json.dumps(enabled)})')
    finally:
        test.browser.close_target(page)
