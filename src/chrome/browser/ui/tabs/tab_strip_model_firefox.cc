// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Firefox's tab placement and selection after closing a tab, ported from
// browser/components/tabbrowser/Tabbrowser.sys.mjs: addTab,
// #insertTabAtIndex, updateCurrentBrowser, _endRemoveTab, #handleTabMove and
// _findTabToBlurTo, and an extension's tabs.create() with openerTabId from
// browser/components/extensions/parent/ext-tabs.js. Firefox's tab `owner` is
// TabModel::firefox_owner(), its #lastRelatedTabMap
// `firefox_last_related_tabs_`. Chromium takes the active tab as the opener of
// every tab a link opens.

#include <algorithm>
#include <optional>
#include <vector>

#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/tabs/oganesson_tab_behavior.h"
#include "chrome/browser/ui/tabs/tab_enums.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/common/pref_names.h"
#include "components/prefs/pref_service.h"
#include "content/public/browser/web_contents.h"
#include "ui/base/page_transition_types.h"
#include "ui/gfx/range/range.h"

namespace oganesson {

void MigrateTabBehaviorPref(PrefService* prefs) {
  if (!prefs->HasPrefPath(kObsoleteTabBehaviorPref)) {
    return;
  }
  if (const int behavior = prefs->GetInteger(kObsoleteTabBehaviorPref)) {
    prefs->SetInteger(kLinkPositionPref, kLinkPositionAfterRelated);
    prefs->SetBoolean(kSelectRelatedOnClosePref, false);
    prefs->SetBoolean(kSelectMRUOnClosePref, behavior == 2);
  }
  prefs->ClearPref(kObsoleteTabBehaviorPref);
}

}  // namespace oganesson

namespace {

// The links knob; a hand-edited value outside the enum counts as Chromium's.
int LinkPosition(const PrefService* prefs) {
  const int value = prefs->GetInteger(oganesson::kLinkPositionPref);
  return value >= oganesson::kLinkPositionChromium &&
                 value <= oganesson::kLinkPositionAtEnd
             ? value
             : oganesson::kLinkPositionChromium;
}

}  // namespace

bool TabStripModel::UsesFirefoxTabRules() const {
  // Any knob off Chromium's value.
  const PrefService* const prefs = profile_->GetPrefs();
  return LinkPosition(prefs) != oganesson::kLinkPositionChromium ||
         !prefs->GetBoolean(oganesson::kSelectRelatedOnClosePref) ||
         !prefs->GetBoolean(oganesson::kSelectOwnerOnClosePref) ||
         prefs->GetBoolean(oganesson::kSelectMRUOnClosePref) ||
         prefs->GetBoolean(prefs::kNewTabNextToActive);
}

bool TabStripModel::FirefoxPlaceNewTab(
    tabs::TabModel* tab,
    ui::PageTransition transition,
    int add_types,
    int* index,
    std::optional<tab_groups::TabGroupId>* group) {
  // Chromium's test for a tab opened from the active tab, see AddTab.
  const bool related = ui::PageTransitionTypeIncludingQualifiersIs(
                           transition, ui::PAGE_TRANSITION_LINK) &&
                       (add_types & ADD_FORCE_INDEX) == 0;
  tabs::TabModel* const selected = GetActiveTabModel();
  // An extension's tabs.create() openerTabId is the tab's owner and opener,
  // for Chromium extensions too: the user chose Firefox's tab behavior.
  auto* const extension_opener =
      static_cast<tabs::TabModel*>(firefox_next_opener_.Get());
  if (extension_opener) {
    // As tabs.create() does once the tab is added, for ChromiumLinkIndex.
    tab->set_opener(extension_opener);
  }
  tabs::TabModel* const opener =
      extension_opener ? extension_opener : (related ? selected : nullptr);
  if (selected) {
    // A foreground tab is owned by the selected tab, and adding any tab ends
    // the selected tab's own owner.
    tab->set_firefox_owner(
        extension_opener ? extension_opener
                         : ((add_types & ADD_ACTIVE) ? selected : nullptr));
    selected->set_firefox_owner(nullptr);
  }

  // Firefox's addTab: the opener's group, also at an index of the caller's.
  if (opener && !group->has_value()) {
    *group = opener->GetGroup();
  }
  if (!related && *index >= 0 && *index <= count()) {
    return false;
  }
  *index = count();
  const int link_position = LinkPosition(profile_->GetPrefs());
  const bool insert_related_after_current =
      link_position == oganesson::kLinkPositionAfterRelated;
  // Helium's "Open new tabs next to the active tab" is Firefox's
  // browser.tabs.insertAfterCurrent.
  if (!selected ||
      !((opener && link_position != oganesson::kLinkPositionAtEnd) ||
        profile_->GetPrefs()->GetBoolean(prefs::kNewTabNextToActive))) {
    return related;
  }

  tabs::TabModel* last_related = nullptr;
  if (opener) {
    auto it = firefox_last_related_tabs_.find(opener->GetHandle());
    if (it != firefox_last_related_tabs_.end()) {
      last_related = static_cast<tabs::TabModel*>(it->second.Get());
    }
  }
  if (opener && link_position == oganesson::kLinkPositionChromium) {
    *index = ChromiumLinkIndex(GetIndexOfTab(opener), add_types & ADD_ACTIVE);
  } else {
    tabs::TabModel* const previous =
        insert_related_after_current && last_related
            ? last_related
            : (opener ? opener : selected);
    if (!group->has_value()) {
      // The opener has none: the group of the tab it goes after.
      *group = previous->GetGroup();
    }
    // browser.tabs.insertAfterCurrentExceptPinned is false: after a pinned
    // tab too, which InsertTabAtImpl turns into the first unpinned position.
    const int previous_index = GetIndexOfTab(previous);
    if (!IsTabCollapsed(previous_index)) {
      *index = previous_index + 1;
    }
  }

  if (last_related) {
    last_related->set_firefox_owner(nullptr);
  } else if (opener) {
    tab->set_firefox_owner(opener);
  }
  if (opener) {
    firefox_last_related_tabs_[opener->GetHandle()] = tab->GetHandle();
  }
  return related;
}

int TabStripModel::ChromiumLinkIndex(int opener_index, bool foreground) const {
  // DetermineInsertionIndex, for any opener.
  if (foreground) {
    return opener_index + 1;
  }
  const int last = GetIndexOfLastWebContentsOpenedBy(
      GetWebContentsAt(opener_index), opener_index);
  if (last == kNoTab) {
    return opener_index + 1;
  }
  // Before the first tab outside the opener's group.
  const std::optional<tab_groups::TabGroupId> opener_group =
      GetTabGroupForTab(opener_index);
  for (int i = opener_index + 1; i <= last; ++i) {
    if (GetTabGroupForTab(i) != opener_group) {
      return i;
    }
  }
  return last + 1;
}

void TabStripModel::FirefoxOnChange(
    const TabStripModelChange& change,
    const TabStripSelectionChange& selection) {
  if (selection.active_tab_changed()) {
    // Leaving a tab ends its owner, and that of the last tab it opened unless
    // that one is selected.
    const int old_index =
        selection.old_tab ? GetIndexOfTab(selection.old_tab) : kNoTab;
    if (old_index != kNoTab) {
      tabs::TabModel* const old_tab = GetTabModelAtIndex(old_index);
      old_tab->set_firefox_owner(nullptr);
      auto it = firefox_last_related_tabs_.find(old_tab->GetHandle());
      auto* const last_related =
          it != firefox_last_related_tabs_.end()
              ? static_cast<tabs::TabModel*>(it->second.Get())
              : nullptr;
      if (last_related && last_related != selection.new_tab) {
        last_related->set_firefox_owner(nullptr);
      }
    }
  }
  // A tab switch, a closed or a moved tab ends the runs of related tabs.
  if (selection.active_tab_changed() ||
      change.type() == TabStripModelChange::kRemoved ||
      change.type() == TabStripModelChange::kMoved) {
    firefox_last_related_tabs_.clear();
  }
}

std::optional<int> TabStripModel::FirefoxTabToSelectOnClose(
    const gfx::Range& block_tabs) const {
  auto outside_block = [&](int i) {
    return !block_tabs.Contains(gfx::Range(i, i + 1));
  };
  auto visible = [&](int i) {
    return !IsTabCollapsed(i);
  };
  auto discarded = [&](int i) { return GetWebContentsAt(i)->WasDiscarded(); };
  const PrefService* const prefs = profile_->GetPrefs();
  // The nearest tab after the block, else the nearest before it.
  auto adjacent = [&](const std::vector<int>& tabs) -> std::optional<int> {
    auto after = std::ranges::find_if(
        tabs, [&](int i) { return i >= static_cast<int>(block_tabs.end()); });
    if (after != tabs.end()) {
      return *after;
    }
    return tabs.empty() ? std::nullopt : std::optional<int>(tabs.back());
  };

  // Chromium's first choices: a tab the block opened, then one its opener
  // opened.
  if (prefs->GetBoolean(oganesson::kSelectRelatedOnClosePref)) {
    for (const int related : {GetIndexOfNextWebContentsOpenedBy(block_tabs),
                              GetIndexOfNextWebContentsOpenedByOpenerOf(
                                  block_tabs)}) {
      if (related != kNoTab && visible(related)) {
        return related;
      }
    }
  }

  // browser.tabs.selectOwnerOnClose: the owner of the active tab, also when a
  // whole group or split closes.
  tabs::TabInterface* const owner =
      prefs->GetBoolean(oganesson::kSelectOwnerOnClosePref) &&
              active_index() != kNoTab && !outside_block(active_index())
          ? GetActiveTabModel()->firefox_owner()
          : nullptr;
  const int owner_index = owner ? GetIndexOfTab(owner) : kNoTab;
  if (owner_index != kNoTab && outside_block(owner_index) &&
      visible(owner_index)) {
    return owner_index;
  }

  std::vector<int> remaining;
  for (int i = 0; i < count(); ++i) {
    if (outside_block(i) && visible(i)) {
      remaining.push_back(i);
    }
  }
  // Discarded tabs are passed over while a loaded one remains.
  if (!std::ranges::all_of(remaining, discarded)) {
    std::erase_if(remaining, discarded);
  }

  if (prefs->GetBoolean(oganesson::kSelectMRUOnClosePref) &&
      !remaining.empty()) {
    return *std::ranges::max_element(remaining, {}, [&](int i) {
      return GetWebContentsAt(i)->GetLastActiveTimeTicks();
    });
  }
  if (std::optional<int> tab = adjacent(remaining)) {
    return tab;
  }

  // A tab in a collapsed group.
  std::vector<int> collapsed;
  for (int i = 0; i < count(); ++i) {
    if (outside_block(i) && IsTabCollapsed(i)) {
      collapsed.push_back(i);
    }
  }
  return adjacent(collapsed);
}
