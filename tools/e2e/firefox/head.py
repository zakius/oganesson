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

from harness import wait_for
from test_google_lens import png

DIR = '/browser/browser/components/extensions/test/browser/'
BASE = f'http://mochi.test:8888{DIR}'

# context.html, with the parts that the ports use: Firefox's has form fields
# and a frame too.
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
    f'{DIR}context_with_redirect.html': (200, {'Content-Type': 'text/html'},
                                         CONTEXT_WITH_REDIRECT_HTML),
    f'{DIR}ctxmenu-image.png': (200, {'Content-Type': 'image/png'}, png(100)),
    f'{DIR}redirect_to.sjs': (302, {'Location': 'ctxmenu-image.png'}, b''),
}

# Firefox's EventUtils modifiers, as xdotool's keys.
MODIFIERS = {'shiftKey': 'shift', 'ctrlKey': 'ctrl', 'altKey': 'alt', 'metaKey': 'super'}


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
    test.browser.click_view(top[0])

    def submenu():
        menus = test.browser.menus()
        return menus[1] if len(menus) > 1 else None
    found = wait_for(submenu, what=f"{name}'s submenu")
    return Menu(test, [item for group in found for item in group])


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
