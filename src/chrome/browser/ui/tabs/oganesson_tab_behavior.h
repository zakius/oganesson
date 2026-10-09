// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_TABS_OGANESSON_TAB_BEHAVIOR_H_
#define CHROME_BROWSER_UI_TABS_OGANESSON_TAB_BEHAVIOR_H_

class PrefService;

// Settings > Behavior > Tab behavior: where new tabs open and which tab is
// selected after closing one (docs/tab-behavior.md). Profile prefs, one per
// knob, defaulting to Chromium's rules; the settings page derives the
// Chromium / Firefox / Custom preset from them. Helium's
// prefs::kNewTabNextToActive, Firefox's browser.tabs.insertAfterCurrent, is
// the fifth knob.
namespace oganesson {

// Where a link opens, a LinkPosition.
inline constexpr char kLinkPositionPref[] = "oganesson.tabs.link_position";
enum LinkPosition {
  // Chromium's DetermineInsertionIndex: a foreground link right after its
  // tab, a background one after the tabs its tab opened before.
  kLinkPositionChromium = 0,
  // Firefox's browser.tabs.insertRelatedAfterCurrent: after its tab and the
  // tabs it opened before.
  kLinkPositionAfterRelated = 1,
  // insertRelatedAfterCurrent false: at the end.
  kLinkPositionAtEnd = 2,
};
// Chromium's first choices on close: a tab the closed one opened, then one
// its opener opened. Firefox has none.
inline constexpr char kSelectRelatedOnClosePref[] =
    "oganesson.tabs.select_related_on_close";
// Firefox's browser.tabs.selectOwnerOnClose.
inline constexpr char kSelectOwnerOnClosePref[] =
    "oganesson.tabs.select_owner_on_close";
// Firefox's browser.tabs.selectMRUOnClose.
inline constexpr char kSelectMRUOnClosePref[] =
    "oganesson.tabs.select_mru_on_close";

// The integer pref the knobs replace: 0 Chromium, 1 Firefox, 2 Firefox with
// selectMRUOnClose.
inline constexpr char kObsoleteTabBehaviorPref[] = "oganesson.tabs.behavior";

// Sets the knobs from kObsoleteTabBehaviorPref and clears it.
void MigrateTabBehaviorPref(PrefService* prefs);

}  // namespace oganesson

#endif  // CHROME_BROWSER_UI_TABS_OGANESSON_TAB_BEHAVIOR_H_
