# Toolbar

Every toolbar item is its own item: the built-in buttons, the location bar, each pinned extension action (page actions included) and each of Chrome's pinned buttons. Any of them moves anywhere on the toolbar by dragging. The order is the profile pref `oganesson.toolbar.items` and survives restarts.

## Showing and hiding

- **Built-in items:** Customize Chrome → Toolbar lists Back, Reload, Address bar, Extensions, Profile and Menu next to Chromium's own switches (Home, Forward, the pinned buttons). Turning one off hides it; turning it on shows it again in its place. The hidden ones are the pref `oganesson.toolbar.hidden`.
- **Extension and page actions:** pin and unpin them in the Extensions menu (the puzzle piece). With the Extensions button hidden, pin them from `chrome://extensions` details instead.
- **Menu hidden:** a right click on an empty part of the toolbar opens the app menu where you clicked.
- **Reset:** Customize toolbar's Reset to default restores the order and shows every hidden item.

## Code

`src/chrome/browser/ui/views/toolbar/toolbar_view_items.cc` orders, drags and hides the items, and opens the menu on a right click. `src/chrome/browser/ui/webui/side_panel/customize_chrome/customize_toolbar/customize_toolbar_oganesson.cc` lists the built-in items in Customize toolbar. `patches/oganesson/ui/toolbar-items.patch` hooks both in.
