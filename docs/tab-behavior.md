# Tab behavior

Settings > Appearance and behavior > Behavior > **Tab behavior** chooses where new tabs open and which tab is selected after closing the active one. A dropdown sets five knobs below it to a preset: **Firefox** (the default) or **Chromium**. Changing a knob shows the preset the knobs now match, or **Custom**.

| Knob | Profile pref | Firefox pref | Firefox | Chromium |
|---|---|---|---|---|
| Open links in new tabs (a dropdown) | `oganesson.tabs.link_position` | `browser.tabs.insertRelatedAfterCurrent` | As in Firefox (1) | As in Chromium (0) |
| Open new tabs next to the active tab (Helium's switch) | `helium.browser.new_tab_next_to_active` | `browser.tabs.insertAfterCurrent` | off | off |
| Closing a tab first selects a tab it opened, or one opened from the same tab | `oganesson.tabs.select_related_on_close` | none, Chromium's rule | off | on |
| Closing a tab returns to the tab that opened it | `oganesson.tabs.select_owner_on_close` | `browser.tabs.selectOwnerOnClose` | on | on |
| Otherwise, closing a tab selects the most recently used tab, not the one on its right | `oganesson.tabs.select_mru_on_close` | `browser.tabs.selectMRUOnClose` | off | off |

The other knobs are switches (on, off). The prefs are the only state: the page derives the preset from them, so it can't disagree with them. The prefs' defaults are the Firefox preset, so a profile with none set gets Firefox's rules. Chromium's and Firefox's defaults differ on two knobs:

- Links: Chromium opens a foreground link right after its tab, and a background link after the tabs its tab opened before. Firefox opens both after those tabs. From `[a] b`, a background link 1 then a foreground link 2 give `a [2] 1 b` in Chromium, `a 1 [2] b` in Firefox. The third value, **At the end**, is `insertRelatedAfterCurrent` false.
- Closing: Chromium first selects a tab the closed one opened, then one its opener opened, then the opener. Firefox selects the owner (the opener, until the user switches tabs), then the next tab.

The presets:

- The Chromium preset runs Chromium's code, unchanged: the hooks in `TabStripModel` return "not handled". An add-on's `tabs.create({openerTabId})` without an `index` opens at the end, as in Chromium.
- Any other combination, the Firefox preset among them, runs Firefox's rules, below, with each knob as its Firefox pref. Chromium's related tabs on close, when on, come before the owner. The links knob's Chromium value places a link with Chromium's rule (`TabStripModel::DetermineInsertionIndex`), so changing only a closing knob keeps Chromium's link order.
- Links from a pinned tab open after the pinned tabs in both (Firefox's `browser.tabs.insertAfterCurrentExceptPinned` is false), so it has no knob.

The Chromium rule for a link, from `DetermineInsertionIndex`: a foreground link opens right after its tab. A background link opens after the last of the unbroken run of tabs right of its tab that its tab opened, directly or through those tabs, or right after its tab when there are none, but before the first tab of that run outside its tab's group. Its tab is the opener of the new tab. A foreground link ends every other tab's opener, and so does selecting a tab with the mouse or keyboard, unless the old and the new tab have the same opener (or none) or one opened the other. So switching to an unrelated tab and back keeps the run, and the next link still goes after the earlier ones. Navigating a tab other than by a link (typing, a bookmark) also ends every opener. The new tab gets its tab's group.

## Why it is shaped this way

Chromium's tab strip model changes often, so the patch stays small. `patches/oganesson/core/firefox-tab-behavior.patch` adds only:

- 2 one-line calls in `tab_strip_model.cc`: `AddTab` and `DetermineNewSelectedIndex`. The rules see other changes as a `TabStripModelObserver`.
- A friend declaration and 2 members in `tab_strip_model.h`.
- A call before and after `OpenTab` in `tabs_api.cc`, to pass `openerTabId`.
- The new file in `BUILD.gn`.

All logic and state (tab owners, the last related tab of each opener) are in `src/chrome/browser/ui/tabs/tab_strip_model_oganesson.cc`, which also reads the knobs. When an update breaks the patch, fix the call sites first. The rules file only depends on `TabStripModel` accessors and `GetTabIndexAfterClosing`, and for the Chromium knob values on `GetIndexOfLastWebContentsOpenedBy`, `GetIndexOfNextWebContentsOpenedBy` and `GetIndexOfNextWebContentsOpenedByOpenerOf`.

The settings plug in like oganesson's other settings: the pref names in `src/chrome/common/oganesson_pref_names.h`, their registration in `src/chrome/browser/prefs/oganesson_prefs.h`, the settings allowlist in `oganesson_prefs_allowlist.h`, the strings in `src/chrome/app/oganesson_tab_strings.grdp` and `oganesson_settings.cc`. The dropdown and knobs are the `settings-tab-behavior` element, `src/chrome/browser/resources/settings/appearance_page/tab_behavior.ts`; `patches/oganesson/settings/tab-behavior-settings.patch` puts it in place of Helium's switch on the Behavior card.

## Firefox's rules

Ported from Firefox's `Tabbrowser.sys.mjs` (`addTab`, `#insertTabAtIndex`, `updateCurrentBrowser`, `_findTabToBlurTo`), `ext-tabs.js` (`tabs.create`) and its tests `browser_new_tab_insert_position.js` and `browser_selectMRUOnClose.js`. The code is `src/chrome/browser/ui/tabs/tab_strip_model_oganesson.cc`.

Where a tab opens:

- A tab opened from a page (a link opened in a new tab, middle click, `window.open`) opens after the current tab, and after the tabs it opened before it, so links opened one after another keep their order (`browser.tabs.insertRelatedAfterCurrent`, the links knob's Firefox value).
- With the links knob's Chromium value they open by Chromium's rule above.
- At the end (without `insertRelatedAfterCurrent`) they open at the end, or with `insertAfterCurrent` right after the current tab, each new one before the last.
- Other new tabs (Ctrl+T, the + button, Alt+Enter in the location bar, bookmarks, an add-on's `tabs.create()` without `openerTabId`) open at the end, or after the current tab with `insertAfterCurrent`.
- An add-on's `tabs.create({openerTabId})` without an `index` is a tab opened from that opener: it opens as the links knob says, in the foreground and in the background, with the Chromium value as a link from the opener. Chromium extensions get the same rule: the setting, not the extension, chooses the behavior. Only the Chromium preset opens it at the end.
- Selecting another tab, closing a tab or moving one ends the run of related tabs: the next link opens right after the current tab again.
- A link from a pinned tab opens after the pinned tabs (`browser.tabs.insertAfterCurrentExceptPinned` is false).

Each tab may have an owner, the tab to select when it closes (`browser.tabs.selectOwnerOnClose`):

- A tab an add-on opens with `openerTabId` is owned by that opener, with or without an `index`. The next one it opens after the opener ends the previous one's owner.
- Any other tab opened in the foreground is owned by the tab selected before it, whatever opened it.
- The first tab a page opens in the background is owned by that page's tab. A second one ends the first one's owner, and has none itself.
- Opening any tab ends the current tab's owner, and so does leaving it for another tab. Leaving a tab also ends the owner of the last tab it opened, unless that is the tab selected.

Closing the active tab selects its owner if it has one (`selectOwnerOnClose`). Otherwise, it selects the next tab, or the one on its left when it was the last tab. Tabs in collapsed groups are passed over, and so are discarded tabs while a loaded one is left. With `selectMRUOnClose`, the most recently used tab is selected instead of the next one, but the owner still comes first. When a whole group or split closes or moves to another window, only the active tab's owner counts, not those of the other tabs in it.

## Sound icon

Tabs don't show the sound icon for a page playing audio unless Settings → Appearance → "Show sound icon on tabs" (`oganesson.tabs.show_audio_indicator`) is on. The muted icon, and the camera, microphone, screen sharing, device, picture-in-picture and VR icons, show either way. The tab's context menu mutes and unmutes the site. Clicking the icon does nothing, as in Chromium, where that needs the EnableTabMuting feature.

`TabAlertController::UpdateAlertState` asks `src/chrome/browser/ui/tabs/alert/oganesson_tab_alerts.cc` before it activates an alert, so the horizontal and vertical tab strips, hover cards, the tab's accessible name and tab search all follow the setting. A per-profile pref observer re-evaluates open tabs when the setting changes. `patches/oganesson/core/tab-audio-indicator.patch` holds the hook; `patches/oganesson/settings/tab-audio-indicator-settings.patch` adds the switch.

## Split view drop target

Dragging a link to the left or right side of the page shows Chromium's split view drop target, a panel with a "+". Dropping the link anywhere on the panel opens it in a new split on that side.

On Wayland, the compositor sends drag motion only while the pointer moves, and drops only on a target that accepted the drag at the last motion. The panel slides in under a resting pointer, so a drop made without moving the pointer again was cancelled: only a drop after moving, for example onto the "+", worked. `patches/oganesson/ui/wayland-drag-resting-pointer.patch` repeats the last drag motion every 350 ms while the pointer rests, as Chromium's X11 drag source does, so the panel takes the drop. Web pages also get `dragover` events while the pointer rests, as the HTML spec requires. `tools/e2e/test_split_view_drop.py` covers the drop on the "+", the drop with a resting pointer and a drop in the middle of the page.
