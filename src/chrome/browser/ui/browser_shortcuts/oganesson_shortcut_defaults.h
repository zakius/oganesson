// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_DEFAULTS_H_
#define CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_DEFAULTS_H_

#include "base/feature_list.h"
#include "chrome/app/chrome_command_ids.h"
#include "chrome/browser/ui/ui_features.h"
#include "chrome/common/pref_names.h"
#include "components/prefs/pref_service.h"

namespace browser_shortcuts {

// Without upstream Ctrl+Tab MRU, the cycle commands run the same tab selection
// as next and previous tab, so list their defaults on one row.
inline int GetDefaultOwner(int command_id, const PrefService* prefs) {
  if (base::FeatureList::IsEnabled(features::kCtrlTabMru) &&
      prefs->GetBoolean(::prefs::kCtrlTabMru)) {
    return command_id;
  }
  switch (command_id) {
    case IDC_CYCLE_TO_NEXT_TAB:
      return IDC_SELECT_NEXT_TAB;
    case IDC_CYCLE_TO_PREV_TAB:
      return IDC_SELECT_PREVIOUS_TAB;
    default:
      return command_id;
  }
}

}  // namespace browser_shortcuts

#endif  // CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_DEFAULTS_H_
