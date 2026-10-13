# Tab behavior

New tabs open, and closing the active tab selects a tab, by Firefox's rules. The rules are always on and have no setting. They match Firefox with its default prefs: `browser.tabs.insertRelatedAfterCurrent` true, `selectOwnerOnClose` true, `selectMRUOnClose` false, `insertAfterCurrentExceptPinned` false. Helium's "Open new tabs next to the active tab" switch stands for `browser.tabs.insertAfterCurrent`.

Chromium extensions get the same rules: an extension's `tabs.create({openerTabId})` without an `index` opens like a link from that opener.

## Why it is shaped this way

Chromium's tab strip model changes often, so the patch stays small. `patches/oganesson/core/firefox-tab-behavior.patch` adds only:

- 2 one-line calls in `tab_strip_model.cc`: `AddTab` and `DetermineNewSelectedIndex`. The rules see other changes as a `TabStripModelObserver`.
- A friend declaration and 2 members in `tab_strip_model.h`.
- A call before and after `OpenTab` in `tabs_api.cc`, to pass `openerTabId`.
- The new file in `BUILD.gn`.

All logic and state (tab owners, the last related tab of each opener) are in `src/chrome/browser/ui/tabs/tab_strip_model_oganesson.cc`. When an update breaks the patch, fix the call sites first. The rules file only depends on public `TabStripModel` accessors and `GetTabIndexAfterClosing`.

## Firefox's rules

Ported from Firefox's `Tabbrowser.sys.mjs` (`addTab`, `#insertTabAtIndex`, `updateCurrentBrowser`, `_findTabToBlurTo`), `ext-tabs.js` (`tabs.create`) and its tests `browser_new_tab_insert_position.js`. The code is `src/chrome/browser/ui/tabs/tab_strip_model_oganesson.cc`.

Where a tab opens:

- A tab opened from a page (a link opened in a new tab, middle click, `window.open`) opens after the current tab, and after the tabs it opened before it, so links opened one after another keep their order (`browser.tabs.insertRelatedAfterCurrent`).
- Other new tabs (Ctrl+T, the + button, Alt+Enter in the location bar, bookmarks, an add-on's `tabs.create()` without `openerTabId`) open at the end, or after the current tab with `insertAfterCurrent`.
- An add-on's `tabs.create({openerTabId})` without an `index` is a tab opened from that opener: it opens after that opener and the tabs it opened before, in the foreground and in the background.
- Selecting another tab, closing a tab or moving one ends the run of related tabs: the next link opens right after the current tab again.
- A link from a pinned tab opens after the pinned tabs (`browser.tabs.insertAfterCurrentExceptPinned` is false).

Each tab may have an owner, the tab to select when it closes (`browser.tabs.selectOwnerOnClose`):

- A tab an add-on opens with `openerTabId` is owned by that opener, with or without an `index`. The next one it opens after the opener ends the previous one's owner.
- Any other tab opened in the foreground is owned by the tab selected before it, whatever opened it.
- The first tab a page opens in the background is owned by that page's tab. A second one ends the first one's owner, and has none itself.
- Opening any tab ends the current tab's owner, and so does leaving it for another tab. Leaving a tab also ends the owner of the last tab it opened, unless that is the tab selected.

Closing the active tab selects its owner if it has one. Otherwise, it selects the next tab, or the one on its left when it was the last tab. Tabs in collapsed groups are passed over, and so are discarded tabs while a loaded one is left. When a whole group or split closes or moves to another window, only the active tab's owner counts, not those of the other tabs in it.

## Sound icon

Tabs don't show the sound icon for a page playing audio unless Settings → Appearance → "Show sound icon on tabs" (`oganesson.tabs.show_audio_indicator`) is on. The muted icon, and the camera, microphone, screen sharing, device, picture-in-picture and VR icons, show either way. The tab's context menu mutes and unmutes the site. Clicking the icon does nothing, as in Chromium, where that needs the EnableTabMuting feature.

`TabAlertController::UpdateAlertState` asks `src/chrome/browser/ui/tabs/alert/oganesson_tab_alerts.cc` before it activates an alert, so the horizontal and vertical tab strips, hover cards, the tab's accessible name and tab search all follow the setting. A per-profile pref observer re-evaluates open tabs when the setting changes. `patches/oganesson/core/tab-audio-indicator.patch` holds the hook; `patches/oganesson/settings/tab-audio-indicator-settings.patch` adds the switch.

## Split view drop target

Dragging a link to the left or right side of the page shows Chromium's split view drop target, a panel with a "+". Dropping the link anywhere on the panel opens it in a new split on that side.

On Wayland, the compositor sends drag motion only while the pointer moves, and drops only on a target that accepted the drag at the last motion. The panel slides in under a resting pointer, so a drop made without moving the pointer again was cancelled: only a drop after moving, for example onto the "+", worked. `patches/oganesson/ui/wayland-drag-resting-pointer.patch` repeats the last drag motion every 350 ms while the pointer rests, as Chromium's X11 drag source does, so the panel takes the drop. Web pages also get `dragover` events while the pointer rests, as the HTML spec requires. `tools/e2e/test_split_view_drop.py` covers the drop on the "+", the drop with a resting pointer and a drop in the middle of the page.
