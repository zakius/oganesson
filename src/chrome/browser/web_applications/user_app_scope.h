// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_WEB_APPLICATIONS_USER_APP_SCOPE_H_
#define CHROME_BROWSER_WEB_APPLICATIONS_USER_APP_SCOPE_H_

#include <optional>
#include <string>
#include <string_view>

#include "components/webapps/common/web_app_id.h"

class GURL;
class PrefService;

namespace web_app {

// Profile pref: per app id, the list of scope rules the user added to the
// app. A rule is a URLPattern constructor string, such as
// "https://*.example.com/*"; one starting with "!" takes the URLs it matches
// out of the scope, the manifest's included.
inline constexpr char kUserAppScopeRules[] =
    "oganesson.web_apps.user_scope_rules";

// Profile pref: per app id, true where the user made the app's scope strict:
// every page out of it leaves the app's window by any route, as an exclusion
// does (out_of_scope_links.h).
inline constexpr char kUserAppStrictScope[] =
    "oganesson.web_apps.strict_scope";

// Whether `url` is in the scope of app `app_id` as the user's rules decide, or
// nullopt where the manifest's scope decides. Include rules add to the
// manifest's scope, except on a host one of them names: there they replace it.
std::optional<bool> UserAppScopeOverride(const PrefService& prefs,
                                         const webapps::AppId& app_id,
                                         const GURL& url);

// App `app_id`'s score for `url` with its rules applied, given its score for
// the manifest's scope, as WebAppRegistrar ranks apps by: 0 if the rules take
// `url` out, `manifest_score` if it is in the manifest's scope, and 1, below
// any manifest scope, if only an include rule has it. The registrar answers
// with this whenever it matches a URL to apps (tab's app, "Open in app",
// intent picker, link capturing), so they follow the rules.
int GetUserAppScopeScore(const PrefService& prefs,
                         const webapps::AppId& app_id,
                         const GURL& url,
                         int manifest_score);

// Whether one of app `app_id`'s exclusions ("!" rules) matches `url`. A page
// in the app's window that reaches such a URL, by any route, is taken out of
// the window (out_of_scope_links.h).
bool IsUrlExcludedFromUserAppScope(const PrefService& prefs,
                                   const webapps::AppId& app_id,
                                   const GURL& url);

// Whether the user made app `app_id`'s scope strict.
bool IsUserAppScopeStrict(const PrefService& prefs,
                          const webapps::AppId& app_id);

void SetUserAppScopeStrict(PrefService& prefs,
                           const webapps::AppId& app_id,
                           bool strict);

// The app's rules, one per line.
std::string GetUserAppScopeRules(const PrefService& prefs,
                                 const webapps::AppId& app_id);

// Sets the app's rules from `rules`, one per line; blank lines are skipped.
// If a rule is invalid, keeps the rules as they were and returns a message
// naming it; otherwise returns an empty string.
std::string SetUserAppScopeRules(PrefService& prefs,
                                 const webapps::AppId& app_id,
                                 std::string_view rules);

}  // namespace web_app

#endif  // CHROME_BROWSER_WEB_APPLICATIONS_USER_APP_SCOPE_H_
