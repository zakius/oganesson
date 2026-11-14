// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_MEDIA_ROUTER_CAST_OPT_IN_H_
#define CHROME_BROWSER_MEDIA_ROUTER_CAST_OPT_IN_H_

#include <memory>

#include "base/supports_user_data.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/common/oganesson_pref_names.h"
#include "components/prefs/pref_service.h"
#include "content/public/browser/browser_context.h"

// Casting's opt-in (Settings > System, oganesson.google.cast_enabled), which
// media_router::MediaRouterEnabled() follows unless a policy decides.
// Header-only, like oganesson_prefs.h: its callers are in different targets.
namespace cast_opt_in {

// Its address keys the answer in the profile's user data.
inline constexpr char kInUseKey[] = "oganesson.cast_in_use";

struct InUse : base::SupportsUserData::Data {
  explicit InUse(bool enabled) : enabled(enabled) {}
  const bool enabled;
};

// Whether casting is on for `context` in this run: the switch as it was when
// first asked, since code set up while casting was off doesn't expect it on.
// Kept on the regular profile, so its incognito profile answers the same, and
// it goes with the profile.
inline bool Enabled(content::BrowserContext* context) {
  Profile* profile = Profile::FromBrowserContext(context)->GetOriginalProfile();
  auto* in_use = static_cast<InUse*>(profile->GetUserData(kInUseKey));
  if (!in_use) {
    auto data = std::make_unique<InUse>(
        profile->GetPrefs()->GetBoolean(prefs::kGoogleCastEnabled));
    in_use = data.get();
    profile->SetUserData(kInUseKey, std::move(data));
  }
  return in_use->enabled;
}

}  // namespace cast_opt_in

#endif  // CHROME_BROWSER_MEDIA_ROUTER_CAST_OPT_IN_H_
