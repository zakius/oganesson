// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_PREFS_OGANESSON_PREFS_H_
#define CHROME_BROWSER_PREFS_OGANESSON_PREFS_H_

#include "base/values.h"
#include "chrome/app/chrome_command_ids.h"
#include "chrome/browser/web_applications/user_app_scope.h"
#include "chrome/browser/web_applications/user_app_start_url.h"
#include "chrome/common/oganesson_pref_names.h"
#include "chrome/common/pref_names.h"
#include "components/omnibox/browser/suggestion_sources.h"
#include "components/pref_registry/pref_registry_syncable.h"

// The profile prefs of every oganesson feature, for RegisterProfilePrefs in
// browser_prefs.cc. Header-only, as browser_prefs.cc is its one caller.
inline void RegisterOganessonProfilePrefs(
    user_prefs::PrefRegistrySyncable* registry) {
  registry->RegisterDictionaryPref(prefs::kMouseGestures,
                                   base::DictValue().Set("L", IDC_BACK));
  registry->RegisterBooleanPref(prefs::kShowTabAudioIndicator, false);
  registry->RegisterListPref(prefs::kToolbarItems);
  registry->RegisterListPref(prefs::kToolbarHiddenItems);
  omnibox::RegisterSuggestionSourcePrefs(registry);
  registry->RegisterDictionaryPref(web_app::kUserAppScopeRules);
  registry->RegisterDictionaryPref(web_app::kUserAppStartUrls);
}

#endif  // CHROME_BROWSER_PREFS_OGANESSON_PREFS_H_
