// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Firefox's tab placement and selection after closing a tab, ported from
// browser/components/tabbrowser/Tabbrowser.sys.mjs: addTab,
// #insertTabAtIndex, updateCurrentBrowser, _endRemoveTab, #handleTabMove and
// _findTabToBlurTo, and an extension's tabs.create() with openerTabId from
// browser/components/extensions/parent/ext-tabs.js. The Firefox prefs these
// rules fix: browser.tabs.insertRelatedAfterCurrent true,
// selectOwnerOnClose true, selectMRUOnClose false and
// insertAfterCurrentExceptPinned false. Helium's "Open new tabs next to the
// active tab" pref stands for browser.tabs.insertAfterCurrent. Chromium takes
// the active tab as the opener of every tab that a link opens.

#include "chrome/browser/ui/tabs/tab_strip_model_oganesson.h"

#include <algorithm>
#include <memory>
#include <optional>
#include <vector>

#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/tabs/tab_enums.h"
#include "chrome/browser/ui/tabs/tab_model.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/common/pref_names.h"
#include "components/prefs/pref_service.h"
#include "content/public/browser/web_contents.h"
#include "ui/base/page_transition_types.h"
#include "ui/gfx/range/range.h"

namespace {

tabs::TabModel* Find(
    const std::map<tabs::TabHandle, tabs::TabHandle>& tabs_by_tab,
    const tabs::TabInterface* tab) {
  auto it = tabs_by_tab.find(tab->GetHandle());
  return it == tabs_by_tab.end()
             ? nullptr
             : static_cast<tabs::TabModel*>(it->second.Get());
}

}  // namespace

// static
OganessonTabRules& OganessonTabRules::Get(TabStripModel& model) {
  if (!model.oganesson_tab_rules_) {
    model.oganesson_tab_rules_ = std::make_unique<OganessonTabRules>();
    model.AddObserver(model.oganesson_tab_rules_.get());
  }
  return *model.oganesson_tab_rules_;
}

tabs::TabInterface* OganessonTabRules::Owner(tabs::TabInterface* tab) const {
  return Find(owners_, tab);
}

void OganessonTabRules::SetOwner(tabs::TabInterface* tab,
                                 tabs::TabInterface* owner) {
  if (owner) {
    owners_[tab->GetHandle()] = owner->GetHandle();
  } else {
    owners_.erase(tab->GetHandle());
  }
}

// static
bool OganessonTabRules::PlaceNewTab(
    TabStripModel& model,
    tabs::TabModel* tab,
    ui::PageTransition transition,
    int add_types,
    int* index,
    std::optional<tab_groups::TabGroupId>* group,
    bool* inherit_opener) {
  OganessonTabRules& rules = Get(model);
  // Chromium's test for a tab opened from the active tab, see AddTab.
  const bool related = ui::PageTransitionTypeIncludingQualifiersIs(
                           transition, ui::PAGE_TRANSITION_LINK) &&
                       (add_types & ADD_FORCE_INDEX) == 0;
  *inherit_opener |= related;
  tabs::TabModel* const selected = model.GetActiveTabModel();
  // An extension's tabs.create() openerTabId is the tab's owner and opener,
  // for Chromium extensions too.
  auto* const extension_opener =
      static_cast<tabs::TabModel*>(model.oganesson_next_opener_.Get());
  if (extension_opener) {
    tab->set_opener(extension_opener);
  }
  tabs::TabModel* const opener =
      extension_opener ? extension_opener : (related ? selected : nullptr);
  if (selected) {
    // A foreground tab is owned by the selected tab, and adding any tab ends
    // the selected tab's own owner.
    rules.SetOwner(tab, extension_opener
                            ? extension_opener
                            : ((add_types & ADD_ACTIVE) ? selected : nullptr));
    rules.SetOwner(selected, nullptr);
  }

  // Firefox's addTab: the opener's group, also at an index of the caller's.
  if (opener && !group->has_value()) {
    *group = opener->GetGroup();
  }
  if (!related && *index >= 0 && *index <= model.count()) {
    return true;
  }
  *index = model.count();
  if (!selected ||
      !(opener || model.profile()->GetPrefs()->GetBoolean(
                      prefs::kNewTabNextToActive))) {
    return true;
  }

  tabs::TabModel* const last_related =
      opener ? Find(rules.last_related_, opener) : nullptr;
  tabs::TabModel* const previous =
      last_related ? last_related : (opener ? opener : selected);
  if (!group->has_value()) {
    // The opener has none: the group of the tab it goes after.
    *group = previous->GetGroup();
  }
  // After a pinned tab too, which InsertTabAtImpl turns into the first
  // unpinned position.
  const int previous_index = model.GetIndexOfTab(previous);
  if (!model.IsTabCollapsed(previous_index)) {
    *index = previous_index + 1;
  }

  if (last_related) {
    rules.SetOwner(last_related, nullptr);
  } else if (opener) {
    rules.SetOwner(tab, opener);
  }
  if (opener) {
    rules.last_related_[opener->GetHandle()] = tab->GetHandle();
  }
  return true;
}

void OganessonTabRules::OnTabStripModelChanged(
    TabStripModel* tab_strip_model,
    const TabStripModelChange& change,
    const TabStripSelectionChange& selection) {
  const TabStripModel& model = *tab_strip_model;
  if (selection.active_tab_changed()) {
    // Leaving a tab ends its owner, and that of the last tab it opened unless
    // that one is selected.
    const int old_index = selection.old_tab
                              ? model.GetIndexOfTab(selection.old_tab)
                              : TabStripModel::kNoTab;
    if (old_index != TabStripModel::kNoTab) {
      tabs::TabModel* const old_tab = model.GetTabModelAtIndex(old_index);
      SetOwner(old_tab, nullptr);
      tabs::TabModel* const last_related = Find(last_related_, old_tab);
      if (last_related && last_related != selection.new_tab) {
        SetOwner(last_related, nullptr);
      }
    }
  }
  // A tab switch, a closed or a moved tab ends the runs of related tabs.
  if (selection.active_tab_changed() ||
      change.type() == TabStripModelChange::kRemoved ||
      change.type() == TabStripModelChange::kMoved) {
    last_related_.clear();
  }
  // Forget the owners of tabs that closed or left for another window.
  if (change.type() == TabStripModelChange::kRemoved) {
    std::erase_if(owners_, [&](const auto& entry) {
      tabs::TabInterface* const tab = entry.first.Get();
      return !tab || model.GetIndexOfTab(tab) == TabStripModel::kNoTab;
    });
  }
}

// static
std::optional<int> OganessonTabRules::NewSelectedIndex(
    const TabStripModel& model,
    const gfx::Range& block_tabs) {
  auto outside_block = [&](int i) {
    return !block_tabs.Contains(gfx::Range(i, i + 1));
  };
  auto visible = [&](int i) { return !model.IsTabCollapsed(i); };
  auto discarded = [&](int i) {
    return model.GetWebContentsAt(i)->WasDiscarded();
  };
  auto after_closing = [&](std::optional<int> i) -> std::optional<int> {
    if (!i) {
      return std::nullopt;
    }
    return model.GetTabIndexAfterClosing(*i, block_tabs);
  };
  // The nearest tab after the block, else the nearest before it.
  auto adjacent = [&](const std::vector<int>& tabs) -> std::optional<int> {
    auto after = std::ranges::find_if(
        tabs, [&](int i) { return i >= static_cast<int>(block_tabs.end()); });
    if (after != tabs.end()) {
      return *after;
    }
    return tabs.empty() ? std::nullopt : std::optional<int>(tabs.back());
  };

  // browser.tabs.selectOwnerOnClose: the owner of the active tab, also when a
  // whole group or split closes.
  const int active = model.active_index();
  tabs::TabInterface* const owner =
      model.oganesson_tab_rules_ && active != TabStripModel::kNoTab &&
              !outside_block(active)
          ? model.oganesson_tab_rules_->Owner(model.GetTabModelAtIndex(active))
          : nullptr;
  const int owner_index =
      owner ? model.GetIndexOfTab(owner) : TabStripModel::kNoTab;
  if (owner_index != TabStripModel::kNoTab && outside_block(owner_index) &&
      visible(owner_index)) {
    return after_closing(owner_index);
  }

  std::vector<int> remaining;
  for (int i = 0; i < model.count(); ++i) {
    if (outside_block(i) && visible(i)) {
      remaining.push_back(i);
    }
  }
  // Discarded tabs are passed over while a loaded one remains.
  if (!std::ranges::all_of(remaining, discarded)) {
    std::erase_if(remaining, discarded);
  }
  if (std::optional<int> tab = adjacent(remaining)) {
    return after_closing(tab);
  }

  // A tab in a collapsed group.
  std::vector<int> collapsed;
  for (int i = 0; i < model.count(); ++i) {
    if (outside_block(i) && model.IsTabCollapsed(i)) {
      collapsed.push_back(i);
    }
  }
  return after_closing(adjacent(collapsed));
}
