// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_WEB_APPLICATIONS_USER_APP_SCOPE_H_
#define CHROME_BROWSER_WEB_APPLICATIONS_USER_APP_SCOPE_H_

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

// Whether `url` is in the scope of app `app_id`, given whether it is in the
// manifest's scope. Include rules add to the manifest's scope, except on a
// host one of them names: there they replace it.
bool IsUrlInUserAppScope(const PrefService& prefs,
                         const webapps::AppId& app_id,
                         const GURL& url,
                         bool in_manifest_scope);

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
