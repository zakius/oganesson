// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// The app settings page's handlers for the user's scope rules and start URL
// of a web app (app_management.mojom).

#include <string>
#include <utility>

#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/webui/app_management/app_management_page_handler_base.h"
#include "chrome/browser/web_applications/user_app_scope.h"
#include "chrome/browser/web_applications/user_app_start_url.h"
#include "chrome/browser/web_applications/web_app_provider.h"
#include "chrome/browser/web_applications/web_app_registrar.h"
#include "url/gurl.h"

void AppManagementPageHandlerBase::GetScopeRules(
    const std::string& app_id,
    GetScopeRulesCallback callback) {
  std::move(callback).Run(
      web_app::GetUserAppScopeRules(*profile_->GetPrefs(), app_id),
      web_app::IsUserAppScopeStrict(*profile_->GetPrefs(), app_id));
}

void AppManagementPageHandlerBase::SetScopeRules(
    const std::string& app_id,
    const std::string& rules,
    bool strict,
    SetScopeRulesCallback callback) {
  std::string error =
      web_app::SetUserAppScopeRules(*profile_->GetPrefs(), app_id, rules);
  if (error.empty()) {
    web_app::SetUserAppScopeStrict(*profile_->GetPrefs(), app_id, strict);
  }
  std::move(callback).Run(error);
}

void AppManagementPageHandlerBase::GetStartUrl(const std::string& app_id,
                                               GetStartUrlCallback callback) {
  web_app::WebAppProvider* provider =
      web_app::WebAppProvider::GetForWebApps(profile_);
  std::move(callback).Run(
      web_app::GetUserAppStartUrlSetting(*profile_->GetPrefs(), app_id),
      provider ? provider->registrar_unsafe().GetAppStartUrl(app_id).spec()
               : std::string());
}

void AppManagementPageHandlerBase::SetStartUrl(const std::string& app_id,
                                               const std::string& url,
                                               SetStartUrlCallback callback) {
  web_app::WebAppProvider* provider =
      web_app::WebAppProvider::GetForWebApps(profile_);
  if (!provider || !web_app::CanHaveUserAppStartUrl(
                       provider->registrar_unsafe().GetAppStartUrl(app_id))) {
    std::move(callback).Run("This app opens at its own start address.");
    return;
  }
  std::move(callback).Run(
      web_app::SetUserAppStartUrl(*profile_->GetPrefs(), app_id, url));
}
