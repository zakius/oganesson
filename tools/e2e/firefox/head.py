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

from extension_test_utils import FirefoxTest
from harness import Page, wait_for
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
    """An open menu's items (MenuItemViews), as they were when it opened."""

    def __init__(self, test, items):
        self.test = test
        self.items = items

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


def open_context_menu(test, page, selector='#img1'):
    """openContextMenu(): a right click on `selector` in `page`, the active
    tab; the context menu that opens."""
    test.browser.click_element(page, selector, button=3)
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
    return Menu(test, [entry for group in found for entry in group])


def close_extension_context_menu(test, item=None, modifiers=None):
    """closeExtensionContextMenu(): a click on `item` with the keys of
    `modifiers` held (Firefox's {shiftKey: true, ...}), or no item to
    close the menu; either way the menus close."""
    if item is None:
        close_context_menu(test)
        return
    keys = [MODIFIERS[name] for name, held in (modifiers or {}).items() if held]
    x, y = item.center
    browser = test.browser
    browser.xdotool('mousemove', str(x), str(y))
    for key in keys:
        browser.xdotool('keydown', key)
    try:
        browser.xdotool('click', '1')
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


def open_chrome_context_menu(test, view):
    """openChromeContextMenu(): a right click on a view of the browser's own
    UI (`view`, from harness.Browser.views()); the context menu that opens."""
    test.browser.click_view(view, button=3)
    menus = open_menus(test)
    return Menu(test, [item for group in menus[0] for item in group])
