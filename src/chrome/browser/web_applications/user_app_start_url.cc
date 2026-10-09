// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/web_applications/user_app_start_url.h"

#include "base/strings/strcat.h"
#include "base/strings/string_util.h"
#include "base/values.h"
#include "components/prefs/pref_service.h"
#include "components/prefs/scoped_user_pref_update.h"
#include "components/webapps/isolated_web_apps/scheme.h"
#include "url/gurl.h"

namespace web_app {

bool CanHaveUserAppStartUrl(const GURL& manifest_start_url) {
  return !manifest_start_url.SchemeIs(webapps::kIsolatedAppScheme);
}

GURL GetUserAppStartUrl(const PrefService& prefs,
                        const webapps::AppId& app_id,
                        const GURL& manifest_start_url) {
  if (!CanHaveUserAppStartUrl(manifest_start_url)) {
    return manifest_start_url;
  }
  // The pref can be edited outside SetUserAppStartUrl (about:config).
  GURL url(GetUserAppStartUrlSetting(prefs, app_id));
  return url.is_valid() && url.SchemeIsHTTPOrHTTPS() ? url
                                                     : manifest_start_url;
}

std::string GetUserAppStartUrlSetting(const PrefService& prefs,
                                      const webapps::AppId& app_id) {
  const std::string* url = prefs.GetDict(kUserAppStartUrls).FindString(app_id);
  return url ? *url : std::string();
}

std::string SetUserAppStartUrl(PrefService& prefs,
                               const webapps::AppId& app_id,
                               std::string_view url) {
  url = base::TrimWhitespaceASCII(url, base::TRIM_ALL);
  GURL gurl(url);
  if (!url.empty() && (!gurl.is_valid() || !gurl.SchemeIsHTTPOrHTTPS())) {
    return base::StrCat({"Not an http or https URL: \"", url, "\""});
  }
  ScopedDictPrefUpdate update(&prefs, kUserAppStartUrls);
  if (url.empty()) {
    update->Remove(app_id);
  } else {
    update->Set(app_id, gurl.spec());
  }
  return std::string();
}

}  // namespace web_app
