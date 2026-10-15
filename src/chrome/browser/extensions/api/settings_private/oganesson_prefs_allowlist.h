// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_EXTENSIONS_API_SETTINGS_PRIVATE_OGANESSON_PREFS_ALLOWLIST_H_
#define CHROME_BROWSER_EXTENSIONS_API_SETTINGS_PRIVATE_OGANESSON_PREFS_ALLOWLIST_H_

#include "chrome/browser/download/download_history_saving.h"
#include "chrome/browser/extensions/api/settings_private/prefs_util.h"
#include "chrome/common/extensions/api/settings_private.h"
#include "chrome/common/oganesson_pref_names.h"
#include "components/history/core/common/pref_names.h"
#include "components/omnibox/browser/suggestion_sources.h"
#include "components/sessions/core/closed_tabs_in_memory.h"

namespace extensions {

// The prefs of oganesson's settings, which the settings pages may read and
// change. Header-only: a source file in a settings target would make a
// dependency cycle with //chrome/browser/extensions, where prefs_util.cc, its
// one caller, is.
inline void AddOganessonPrefsToAllowlist(PrefsUtil::TypedPrefMap& allowlist) {
  using api::settings_private::PrefType;
  allowlist[::prefs::kMouseGestures] = PrefType::kDictionary;
  allowlist[::prefs::kShowTabAudioIndicator] = PrefType::kBoolean;
  allowlist[::prefs::kTabLinkPosition] = PrefType::kNumber;
  for (const char* pref :
       {::prefs::kTabSelectRelatedOnClose, ::prefs::kTabSelectOwnerOnClose,
        ::prefs::kTabSelectMRUOnClose}) {
    allowlist[pref] = PrefType::kBoolean;
  }
  allowlist[::prefs::kSavingBrowserHistoryDisabled] = PrefType::kBoolean;
  allowlist[::prefs::kSavingDownloadHistoryDisabled] = PrefType::kBoolean;
  allowlist[::sessions::kKeepClosedTabsInMemory] = PrefType::kBoolean;
  for (const char* pref :
       {::omnibox::kSuggestHistory, ::omnibox::kSuggestBookmarks,
        ::omnibox::kSuggestOpenTabs, ::omnibox::kSuggestPastSearches}) {
    allowlist[pref] = PrefType::kBoolean;
  }
  allowlist[::omnibox::kSuggestionOrder] = PrefType::kList;
}

}  // namespace extensions

#endif  // CHROME_BROWSER_EXTENSIONS_API_SETTINGS_PRIVATE_OGANESSON_PREFS_ALLOWLIST_H_
