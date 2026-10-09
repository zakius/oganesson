# Tab behavior

Settings > Appearance > Behavior > **Tab behavior** chooses where new tabs open and which tab is selected after closing the active one. A dropdown sets five knobs below it to a preset: **Chromium** (the default) or **Firefox**. Changing a knob shows the preset the knobs now match, or **Custom**.

| Knob | Profile pref | Firefox pref | Chromium | Firefox |
|---|---|---|---|---|
| Open links in new tabs (a dropdown) | `oganesson.tabs.link_position` | `browser.tabs.insertRelatedAfterCurrent` | As in Chromium (0) | As in Firefox (1) |
| Open new tabs next to the active tab (Helium's switch) | `helium.browser.new_tab_next_to_active` | `browser.tabs.insertAfterCurrent` | off | off |
| Closing a tab first selects a tab it opened, or one opened from the same tab | `oganesson.tabs.select_related_on_close` | none, Chromium's rule | on | off |
| Closing a tab returns to the tab that opened it | `oganesson.tabs.select_owner_on_close` | `browser.tabs.selectOwnerOnClose` | on | on |
| Otherwise, closing a tab selects the most recently used tab, not the one on its right | `oganesson.tabs.select_mru_on_close` | `browser.tabs.selectMRUOnClose` | off | off |

The other knobs are switches (on, off). The prefs are the only state: the page derives the preset from them, so it can't disagree with them. Chromium's and Firefox's defaults differ on two knobs:

- Links: Chromium opens a foreground link right after its tab, and a background link after the tabs its tab opened before. Firefox opens both after those tabs. From `[a] b`, a background link 1 then a foreground link 2 give `a [2] 1 b` in Chromium, `a 1 [2] b` in Firefox. The third value, **At the end**, is `insertRelatedAfterCurrent` false.
- Closing: Chromium first selects a tab the closed one opened, then one its opener opened, then the opener. Firefox selects the owner (the opener, until the user switches tabs), then the next tab.

The presets:

- The Chromium preset runs Chromium's code, unchanged. An add-on's `tabs.create({openerTabId})` without an `index` opens at the end, as in Chromium.
- Any other combination runs Firefox's rules, below, with each knob as its Firefox pref. Chromium's related tabs on close, when on, come before the owner. The links knob's Chromium value places a link with Chromium's rule (`TabStripModel::DetermineInsertionIndex`), so changing only a closing knob keeps Chromium's link order.
- Links from a pinned tab open after the pinned tabs in both (Firefox's `browser.tabs.insertAfterCurrentExceptPinned` is false), so it has no knob.

The Chromium rule for a link, from `DetermineInsertionIndex`: a foreground link opens right after its tab. A background link opens after the last of the unbroken run of tabs right of its tab that its tab opened, directly or through those tabs, or right after its tab when there are none, but before the first tab of that run outside its tab's group. Its tab is the opener of the new tab. A foreground link ends every other tab's opener, and so does selecting a tab with the mouse or keyboard, unless the old and the new tab have the same opener (or none) or one opened the other. So switching to an unrelated tab and back keeps the run, and the next link still goes after the earlier ones. Navigating a tab other than by a link (typing, a bookmark) also ends every opener. The new tab gets its tab's group.

The integer pref `oganesson.tabs.behavior` this replaces is migrated at startup and cleared: Chromium (0) keeps the Chromium preset, Firefox (1) becomes the Firefox preset, Firefox with the most recently used tab on close (2) the Firefox preset with the last switch on, shown as Custom.

## Firefox's rules

Ported from Firefox's `Tabbrowser.sys.mjs` (`addTab`, `#insertTabAtIndex`, `updateCurrentBrowser`, `_findTabToBlurTo`), `ext-tabs.js` (`tabs.create`) and its tests `browser_new_tab_insert_position.js` and `browser_selectMRUOnClose.js`. The code is `src/chrome/browser/ui/tabs/tab_strip_model_firefox.cc`.

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

Closing the active tab selects its owner if it has one (`selectOwnerOnClose`). Otherwise, it selects the next tab, or the one on its left when it was the last tab. Tabs hidden by an add-on (`tabs.hide()`) and tabs in collapsed groups are passed over, and so are discarded tabs while a loaded one is left. With `selectMRUOnClose`, the most recently used tab is selected instead of the next one, but the owner still comes first. When a whole group or split closes or moves to another window, only the active tab's owner counts, not those of the other tabs in it.
