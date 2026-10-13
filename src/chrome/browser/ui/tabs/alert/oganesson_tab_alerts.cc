// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/tabs/alert/oganesson_tab_alerts.h"

#include <memory>

#include "base/functional/bind.h"
#include "base/supports_user_data.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/recently_audible_helper.h"
#include "chrome/common/pref_names.h"
#include "components/prefs/pref_change_registrar.h"
#include "components/prefs/pref_service.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/web_contents.h"

namespace tabs {

namespace {

const char kWatcherKey[] = "OganessonAudioIndicatorWatcher";

Profile* ProfileOf(const TabInterface& tab) {
  return Profile::FromBrowserContext(tab.GetContents()->GetBrowserContext());
}

// One pref observer per profile, shared by its tabs.
class Watcher : public base::SupportsUserData::Data {
 public:
  explicit Watcher(PrefService* prefs) {
    registrar_.Init(prefs);
    registrar_.Add(prefs::kShowTabAudioIndicator,
                   base::BindRepeating(
                       [](base::RepeatingClosureList* callbacks) {
                         callbacks->Notify();
                       },
                       &callbacks_));
  }

  base::RepeatingClosureList callbacks_;

 private:
  PrefChangeRegistrar registrar_;
};

}  // namespace

bool OganessonShowsAlert(const TabInterface& tab, TabAlert alert) {
  return alert != TabAlert::kAudioPlaying ||
         ProfileOf(tab)->GetPrefs()->GetBoolean(prefs::kShowTabAudioIndicator);
}

base::CallbackListSubscription OganessonOnAudioIndicatorChanged(
    TabInterface& tab,
    base::RepeatingCallback<void(bool)> callback) {
  Profile* profile = ProfileOf(tab);
  auto* watcher = static_cast<Watcher*>(profile->GetUserData(kWatcherKey));
  if (!watcher) {
    auto owned = std::make_unique<Watcher>(profile->GetPrefs());
    watcher = owned.get();
    profile->SetUserData(kWatcherKey, std::move(owned));
  }
  // The tab outlives the subscription, which its TabAlertController owns.
  return watcher->callbacks_.Add(base::BindRepeating(
      [](TabInterface* tab, base::RepeatingCallback<void(bool)> callback) {
        callback.Run(RecentlyAudibleHelper::FromWebContents(tab->GetContents())
                         ->WasRecentlyAudible());
      },
      base::Unretained(&tab), std::move(callback)));
}

}  // namespace tabs
