// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef COMPONENTS_SESSIONS_CORE_CLOSED_TABS_IN_MEMORY_H_
#define COMPONENTS_SESSIONS_CORE_CLOSED_TABS_IN_MEMORY_H_

#include "components/history/core/common/pref_names.h"
#include "components/prefs/pref_service.h"

namespace sessions {

// While history.saving_disabled is on, whether closed tabs and windows are
// still kept in memory until the browser closes, so they can be reopened.
// They're never written to disk then.
inline constexpr char kKeepClosedTabsInMemory[] =
    "oganesson.history.keep_closed_tabs";

// Whether closed tabs and windows are kept to reopen: history is saved, or
// it isn't and they're kept in memory.
inline bool KeepsClosedTabs(const PrefService& prefs) {
  return !prefs.GetBoolean(prefs::kSavingBrowserHistoryDisabled) ||
         prefs.GetBoolean(kKeepClosedTabsInMemory);
}

}  // namespace sessions

#endif  // COMPONENTS_SESSIONS_CORE_CLOSED_TABS_IN_MEMORY_H_
