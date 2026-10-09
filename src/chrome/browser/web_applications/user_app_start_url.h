// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_WEB_APPLICATIONS_USER_APP_START_URL_H_
#define CHROME_BROWSER_WEB_APPLICATIONS_USER_APP_START_URL_H_

#include <string>
#include <string_view>

#include "components/webapps/common/web_app_id.h"

class GURL;
class PrefService;

namespace web_app {

// Profile pref: per app id, the URL the user set for the app to open at, in
// place of the manifest's start_url.
inline constexpr char kUserAppStartUrls[] = "oganesson.web_apps.user_start_urls";

// Whether the app whose manifest start URL is `manifest_start_url` takes a
// start URL from the user: isolated web apps and their sub-apps don't.
bool CanHaveUserAppStartUrl(const GURL& manifest_start_url);

// The URL app `app_id` opens at: the user's, if the app can have one and it is
// an http or https URL, or else `manifest_start_url`.
GURL GetUserAppStartUrl(const PrefService& prefs,
                        const webapps::AppId& app_id,
                        const GURL& manifest_start_url);

// The user's start URL for the app, or an empty string.
std::string GetUserAppStartUrlSetting(const PrefService& prefs,
                                      const webapps::AppId& app_id);

// Sets the user's start URL for the app; an empty `url` removes it. If `url`
// isn't an http or https URL, keeps the old one and returns a message saying
// so; otherwise returns an empty string.
std::string SetUserAppStartUrl(PrefService& prefs,
                               const webapps::AppId& app_id,
                               std::string_view url);

}  // namespace web_app

#endif  // CHROME_BROWSER_WEB_APPLICATIONS_USER_APP_START_URL_H_
