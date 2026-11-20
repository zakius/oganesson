"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_contextMenus_icons.js.

Firefox reads the URL of a menu item's image (its `image` attribute); this
browser's menu items have no URL, so each image file of the test is a PNG
of a colour of its own (IMAGES), and the port reads the colour of the icon
that the item shows on the screen (icon_of()). child4's icon, an SVG data:
URL, is a black square. Firefox's top-level menu of an add-on
("top-level-menu") is, in this browser, the item with the add-on's name.
"""

from firefox import head
from extension_test_utils import JS
from test_importer import png

PAGE = f'{head.BASE}context.html?test=icons'

# child4's icon in test_child_icon, an SVG data: URL.
SVG_ICON = 'the SVG data: URL'

# The colour of each image: none black but the SVG's.
IMAGES = {
    'extension.png': (255, 128, 0),
    'black_icon.png': (128, 0, 128),
    'red_icon.png': (255, 0, 0),
    'blue_icon.png': (0, 0, 255),
    'green_icon.png': (0, 255, 0),
    'red.png': (192, 0, 0),
    'green.png': (0, 192, 0),
    SVG_ICON: (0, 0, 0),
}


def image_files(*names):
    """The add-on's image files `names`."""
    return {name: png(IMAGES[name]) for name in names}


def icon_of(test, item):
    """getAttribute("image") of `item`: the name of the image of IMAGES whose
    colour its icon shows, a description of an icon of another colour (such
    as this browser's puzzle piece for an add-on without icons), or None
    when it shows no icon. The icon is the image at the item's start
    (head.check_image()); an item without one has no image there."""
    image = head.check_image(test, item)
    if image is None or not image.visible:
        return None
    colour = test.browser.pixel(*image.center)
    return next((name for name, rgb in IMAGES.items() if tuple(rgb) == colour),
                f'an icon of colour {colour}')


class ContextMenusIconsTest(head.ContextMenuTest):

    def test_root_icon(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'name': 'contextMenus icons',
                'permissions': ['contextMenus'],
                'icons': {
                    '18': 'extension.png',
                },
            },
            files=image_files('extension.png'),
            background=JS('''function () {
              let menuitemId = browser.contextMenus.create({
                title: "child-to-delete",
                onclick: () => {
                  browser.contextMenus.remove(menuitemId);
                  browser.test.sendMessage("child-deleted");
                },
              });

              browser.contextMenus.create(
                {
                  title: "child",
                },
                () => {
                  browser.test.sendMessage("contextmenus-icons");
                }
              );
            }'''))

        def confirm_context_menu_icon(root_elements):
            self.is_(len(root_elements), 1, 'Found exactly one menu item')
            self.check(bool(root_elements) and icon_of(self, root_elements[0]) == 'extension.png',
                       'The context menu should display the extension icon next to the root element')

        extension.startup()
        extension.await_message('contextmenus-icons')

        # openExtensionContextMenu(), with the top-level menu read first.
        context_menu = head.open_context_menu(self, tab)
        top_level_menu_item = context_menu.by_label('contextMenus icons')
        confirm_context_menu_icon(top_level_menu_item)
        extension_menu = head.open_submenu(self, top_level_menu_item[0])

        child_to_delete = extension_menu.by_label('child-to-delete')
        self.is_(len(child_to_delete), 1, 'Found exactly one child to delete')
        head.close_extension_context_menu(self, child_to_delete[0])
        extension.await_message('child-deleted')

        # openExtensionContextMenu(): the add-on's one item is in the context
        # menu itself.
        context_menu = head.open_context_menu(self, tab)
        top_level_menu_item = context_menu.by_label('child')

        confirm_context_menu_icon(top_level_menu_item)
        head.close_context_menu(self)

        extension.unload()
        self.browser.close_target(tab)

    def test_child_icon(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
                'icons': {
                    '18': 'black_icon.png',
                },
            },
            files=image_files('black_icon.png', 'red_icon.png', 'blue_icon.png',
                              'green_icon.png'),
            background=JS('''function () {
              browser.test.onMessage.addListener(msg => {
                if (msg !== "add-additional-contextmenu-items") {
                  return;
                }

                browser.contextMenus.create({
                  title: "child2",
                  id: "contextmenu-child2",
                  icons: {
                    18: "blue_icon.png",
                  },
                });

                browser.contextMenus.create({
                  title: "child3",
                  id: "contextmenu-child3",
                  icons: {
                    18: "green_icon.png",
                  },
                });

                // See bug 1986618
                browser.contextMenus.create(
                  {
                    title: "child4",
                    id: "contextmenu-child4",
                    icons: {
                      16: "data:image/svg+xml,%3csvg width='16' height='16' xmlns='http://www.w3.org/2000/svg'%3e %3crect width='16' height='16' style='fill:black' /%3e %3ctext x='50%25' y='59%25' font-size='0.7em' fill='black' dominant-baseline='middle' text-anchor='middle' font-family='sans-serif'%3eH%3c/text%3e %3c/svg%3e",
                    },
                  },
                  () => {
                    browser.test.sendMessage("extra-contextmenu-items-added");
                  }
                );
              });

              browser.contextMenus.create(
                {
                  title: "child1",
                  id: "contextmenu-child1",
                  icons: {
                    18: "red_icon.png",
                  },
                },
                () => {
                  browser.test.sendMessage("single-contextmenu-item-added");
                }
              );
            }'''))

        def confirm_context_menu_icon(element, image_name):
            self.check(icon_of(self, element) == image_name,
                       'The context menu should display the extension icon next to the child element')

        extension.startup()

        extension.await_message('single-contextmenu-item-added')

        context_menu = head.open_context_menu(self, tab)
        context_menu_child1 = context_menu.by_label('child1')[0]
        confirm_context_menu_icon(context_menu_child1, 'black_icon.png')

        head.close_context_menu(self)

        extension.send_message('add-additional-contextmenu-items')
        extension.await_message('extra-contextmenu-items-added')

        context_menu = head.open_extension_context_menu(self, tab)

        context_menu_child1 = context_menu.by_label('child1')[0]
        confirm_context_menu_icon(context_menu_child1, 'red_icon.png')

        context_menu_child2 = context_menu.by_label('child2')[0]
        confirm_context_menu_icon(context_menu_child2, 'blue_icon.png')

        context_menu_child3 = context_menu.by_label('child3')[0]
        confirm_context_menu_icon(context_menu_child3, 'green_icon.png')

        context_menu_child4 = context_menu.by_label('child4')[0]
        self.is_(icon_of(self, context_menu_child4), SVG_ICON, "child4's icon")
        head.close_context_menu(self)

        extension.unload()
        self.browser.close_target(tab)

    def test_manifest_without_icons(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'name': 'contextMenus icons',
                'permissions': ['contextMenus'],
            },
            files=image_files('red.png', 'green.png'),
            background=JS('''function () {
              browser.contextMenus.create(
                {
                  title: "first item",
                  icons: {
                    18: "red.png",
                  },
                  onclick() {
                    browser.contextMenus.create(
                      {
                        title: "second item",
                        icons: {
                          18: "green.png",
                        },
                      },
                      () => {
                        browser.test.sendMessage("added-second-item");
                      }
                    );
                  },
                },
                () => {
                  browser.test.sendMessage("contextmenus-icons");
                }
              );
            }'''))

        extension.startup()
        extension.await_message('contextmenus-icons')

        menu = head.open_context_menu(self, tab)
        items = menu.by_label('first item')
        self.is_(len(items), 1, 'Found first item')
        # manifest.json does not declare icons, so the root menu item shouldn't have an icon either.
        self.is_(icon_of(self, items[0]), None, 'Root menu must not have an icon')

        head.close_extension_context_menu(self, items[0])
        extension.await_message('added-second-item')

        # openExtensionContextMenu(), with the top-level menu read first.
        context_menu = head.open_context_menu(self, tab)
        items = context_menu.by_label('contextMenus icons')
        self.is_(len(items), 1, 'Auto-generated root item exists')
        self.is_(icon_of(self, items[0]) if items else None, None,
                 'Auto-generated menu root must not have an icon')
        menu = head.open_submenu(self, items[0])

        items = menu.by_label('first item')
        self.is_(len(items), 1, 'First child item should exist')
        self.is_(icon_of(self, items[0]) if items else None, 'red.png',
                 'First item should have an icon')

        items = menu.by_label('second item')
        self.is_(len(items), 1, 'Second child item should exist')
        self.is_(icon_of(self, items[0]) if items else None, 'green.png',
                 'Second item should have an icon')

        head.close_extension_context_menu(self)
        extension.unload()
        self.browser.close_target(tab)

    def test_child_icon_update(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['contextMenus'],
                'icons': {
                    '18': 'black_icon.png',
                },
            },
            files=image_files('black_icon.png', 'red_icon.png', 'blue_icon.png'),
            background=JS('''function () {
              browser.test.onMessage.addListener(msg => {
                if (msg === "update-contextmenu-item") {
                  browser.contextMenus.update(
                    "contextmenu-child2",
                    {
                      icons: {
                        18: "blue_icon.png",
                      },
                    },
                    () => {
                      browser.test.sendMessage("contextmenu-item-updated");
                    }
                  );
                } else if (msg === "update-contextmenu-item-without-icons") {
                  browser.contextMenus.update("contextmenu-child2", {}, () => {
                    browser.test.sendMessage("contextmenu-item-updated-without-icons");
                  });
                } else if (msg === "update-contextmenu-item-with-icons-as-null") {
                  browser.contextMenus.update(
                    "contextmenu-child2",
                    {
                      icons: null,
                    },
                    () => {
                      browser.test.sendMessage(
                        "contextmenu-item-updated-with-icons-as-null"
                      );
                    }
                  );
                } else if (msg === "update-contextmenu-item-when-its-the-only-child") {
                  browser.contextMenus.update(
                    "contextmenu-child1",
                    {
                      icons: {
                        18: "blue_icon.png",
                      },
                    },
                    () => {
                      browser.test.sendMessage(
                        "contextmenu-item-updated-when-its-only-child"
                      );
                    }
                  );
                }
              });

              browser.contextMenus.create({
                title: "child1",
                id: "contextmenu-child1",
                icons: {
                  18: "blue_icon.png",
                },
              });

              let menuitemId = browser.contextMenus.create(
                {
                  title: "child2",
                  id: "contextmenu-child2",
                  icons: {
                    18: "red_icon.png",
                  },
                  onclick: async () => {
                    await browser.contextMenus.remove(menuitemId);
                    browser.test.sendMessage("child-deleted");
                  },
                },
                () => {
                  browser.test.sendMessage("contextmenu-items-added");
                }
              );
            }'''))

        def confirm_context_menu_icon(element, image_name):
            self.check(icon_of(self, element) == image_name,
                       'The context menu should display the extension icon next to the child element')

        extension.startup()

        extension.await_message('contextmenu-items-added')
        context_menu = head.open_extension_context_menu(self, tab)

        context_menu_child1 = context_menu.by_label('child1')[0]
        confirm_context_menu_icon(context_menu_child1, 'blue_icon.png')

        context_menu_child2 = context_menu.by_label('child2')[0]
        confirm_context_menu_icon(context_menu_child2, 'red_icon.png')

        head.close_context_menu(self)

        extension.send_message('update-contextmenu-item')
        extension.await_message('contextmenu-item-updated')

        context_menu = head.open_extension_context_menu(self, tab)

        context_menu_child2 = context_menu.by_label('child2')[0]
        confirm_context_menu_icon(context_menu_child2, 'blue_icon.png')

        head.close_context_menu(self)

        extension.send_message('update-contextmenu-item-without-icons')
        extension.await_message('contextmenu-item-updated-without-icons')

        context_menu = head.open_extension_context_menu(self, tab)

        context_menu_child2 = context_menu.by_label('child2')[0]
        confirm_context_menu_icon(context_menu_child2, 'blue_icon.png')

        head.close_context_menu(self)

        extension.send_message('update-contextmenu-item-with-icons-as-null')
        extension.await_message('contextmenu-item-updated-with-icons-as-null')

        context_menu = head.open_extension_context_menu(self, tab)

        context_menu_child2 = context_menu.by_label('child2')[0]
        self.is_(icon_of(self, context_menu_child2), None, 'Second child should not have an icon')

        head.close_extension_context_menu(self, context_menu_child2)
        extension.await_message('child-deleted')

        context_menu = head.open_context_menu(self, tab)

        context_menu_child1 = context_menu.by_label('child1')[0]
        confirm_context_menu_icon(context_menu_child1, 'black_icon.png')

        head.close_context_menu(self)

        extension.send_message('update-contextmenu-item-when-its-the-only-child')
        extension.await_message('contextmenu-item-updated-when-its-only-child')

        context_menu = head.open_context_menu(self, tab)

        context_menu_child1 = context_menu.by_label('child1')[0]
        confirm_context_menu_icon(context_menu_child1, 'black_icon.png')

        head.close_context_menu(self)

        extension.unload()
        self.browser.close_target(tab)
