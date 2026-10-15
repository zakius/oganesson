// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_TABS_TAB_STRIP_MODEL_OGANESSON_H_
#define CHROME_BROWSER_UI_TABS_TAB_STRIP_MODEL_OGANESSON_H_

#include <map>
#include <optional>

#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/browser/ui/tabs/tab_strip_model_observer.h"
#include "components/tab_groups/tab_group_id.h"
#include "components/tabs/public/tab_interface.h"
#include "ui/base/page_transition_types.h"

namespace gfx {
class Range;
}

// Firefox's rules for where a new tab opens and which tab is selected when
// the active one closes, with Settings > Behavior > Tab behavior's knobs as
// their Firefox prefs (docs/tab-behavior.md). Under the Chromium preset the
// hooks return "not handled" and Chromium's code runs unchanged.
// TabStripModel calls the static functions from AddTab and
// DetermineNewSelectedIndex; the rules observe the model from the first tab
// they place on, which is when they get state to drop. All other state lives
// here rather than in TabStripModel or TabModel, which keeps the Chromium
// patch to a few lines.
class OganessonTabRules : public TabStripModelObserver {
 public:
  // An extension's tabs.create({openerTabId}) names the opener of the tab
  // that it adds next. Pass nullptr after the tab is added.
  static void SetNextOpener(TabStripModel& model, tabs::TabInterface* opener) {
    model.oganesson_next_opener_ =
        opener ? opener->GetHandle() : tabs::TabHandle();
  }

  // Sets the index and group of a tab that AddTab adds, and whether the tab
  // inherits its opener, and returns true. Returns false under the Chromium
  // preset, for Chromium's placement.
  static bool PlaceNewTab(TabStripModel& model,
                          tabs::TabModel* tab,
                          ui::PageTransition transition,
                          int add_types,
                          int* index,
                          std::optional<tab_groups::TabGroupId>* group,
                          bool* inherit_opener);

  // TabStripModelObserver:
  void OnTabStripModelChanged(
      TabStripModel* tab_strip_model,
      const TabStripModelChange& change,
      const TabStripSelectionChange& selection) override;

  // The index to select after `block_tabs` close, or nullopt to let Chromium
  // choose, as it always does under the Chromium preset.
  static std::optional<int> NewSelectedIndex(const TabStripModel& model,
                                             const gfx::Range& block_tabs);

 private:
  static OganessonTabRules& Get(TabStripModel& model);

  // Chromium's DetermineInsertionIndex for a link from any opener.
  static int ChromiumLinkIndex(const TabStripModel& model,
                               int opener_index,
                               bool foreground);

  tabs::TabInterface* Owner(tabs::TabInterface* tab) const;
  void SetOwner(tabs::TabInterface* tab, tabs::TabInterface* owner);

  // Firefox's tab `owner`: the tab to select when a tab closes.
  std::map<tabs::TabHandle, tabs::TabHandle> owners_;
  // Firefox's #lastRelatedTabMap: the last tab each opener opened since the
  // last tab switch. The next related tab opens after it.
  std::map<tabs::TabHandle, tabs::TabHandle> last_related_;
};

#endif  // CHROME_BROWSER_UI_TABS_TAB_STRIP_MODEL_OGANESSON_H_
