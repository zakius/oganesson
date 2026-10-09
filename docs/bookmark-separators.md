# Bookmark separators

A separator is a line between bookmarks, as in Firefox (#160). It is a node of its own in the bookmark model (`BookmarkNode::SEPARATOR`), not a bookmark with a made-up URL: it has no URL, no title and no children, and nothing can be added into it. Profiles store it in `Bookmarks` as `"type": "separator"`.

## Where it shows

- **Bookmarks bar**: a vertical line like the bar's own separators. A click opens nothing. It has the bookmark context menu (no Edit) and drags like a bookmark.
- **Bookmark menus** (bar folders, the overflow chevron, "All bookmarks", the app menu's bookmarks): a menu separator line.
- **Bookmark manager** (`chrome://bookmarks`): a row with a line, named "Separator" for screen readers. It can be selected, cut, copied, pasted, dragged and deleted; Edit is off and opening it does nothing. The folder tree doesn't list it.
- **Side panel bookmarks**: a line row in the "Custom order" sort, which lists bookmarks in their own order, as on the bar, without putting folders first. A click on the row opens nothing, it has no checkbox in edit mode and no context menu, and a bookmark dropped on it goes into its folder. The other sorts (Newest, Oldest, Last opened, A to Z, Z to A) and searches don't show separators: in a sorted list a separator has no place to keep. Firefox's Library also hides separators when it sorts. Newest stays the default.
- **HTML export and import**: `<HR>`, as Firefox writes it. An import makes each `<HR>` a separator in its place.

**Sort by name** sorts each section between separators on its own, folders first, and leaves the separators in place, as Firefox does.

## Adding one

"Add separator", Firefox's New Separator, is in the context menu of bookmarks and folders on the bookmarks bar, in bookmark menus and in the side panel's native menu, and in the bookmark manager's menus. On a bookmark or a separator it inserts the separator after it; on a folder (on the bar, in a menu) or on the manager's empty list area or its toolbar menu, at the end of the folder. In the manager, a folder in the list counts as an item: the separator goes after it. It is off where adding a bookmark is off: in managed (policy) folders and with bookmark editing turned off. Undo removes it like other adds, and Chromium extensions get no event for it.

Separators also come from Firefox add-ons, Firefox Sync, HTML import and the Firefox and Floorp importers. Copying one keeps it a separator.

## Extensions

- **Firefox add-ons** get Firefox's shape: `type: "separator"`, `title: ""` and `url: "data:"` (in API output only) from `get`, `getChildren`, `getTree`, `getSubTree`, `search`, `create`, `move`, `update`, and in `onCreated` and `onRemoved`, whose nodes have Firefox's `type` for every node. `create({type: "separator"})` makes one, ignoring a URL; a separator with a title is refused, and so is `update` with a title or URL ("Invalid value for property 'title'.", as Firefox). A separator is no parent for `create` or `move`.
- **Chromium extensions** don't see separators. Decision: Chromium's API has no separator nodes, and a Chromium extension reading a node without a URL takes it for a folder, so they are left out instead of shown in some made-up form. They aren't in any list or tree, an ID lookup fails with "Can't find bookmark for id.", there are no events for them, and `onChildrenReordered` leaves their IDs out. Other nodes keep their real `index`, so a folder of a bookmark, a separator and a bookmark gives indexes 0 and 2. A Chromium extension can't create one (`type` is refused).
- **WebUI pages** using `chrome.bookmarks` see separators with `type: "separator"` and nothing else of Firefox's shape.

## Sync and import

- **Firefox Sync** carries separators both ways, with their Firefox GUID kept in the node's meta info like other nodes (see [`firefox-sync.md`](firefox-sync.md)). Separators the sync store had from before, which the browser never got, aren't deleted from Firefox: they come down with the next sync, in their places.
- **Firefox and Floorp import** keep each separator in its place in its folder. The importer skips the install's default bookmarks by URL, and only bookmarks: an empty folder there, whose entry has no URL, doesn't make it skip separators (or empty folders).
- Helium's own sync is dormant (patched out); if it ran, separators wouldn't be synced by it (`BookmarkModelView::IsNodeSyncable()`).

Verified by `./oganesson.py test bookmark_separators` (also Add separator on each surface, the side panel's custom order and HTML import), `amo_livemarks` (Livemarks puts one after a feed's site link), `importer` and `firefox_sync`.
