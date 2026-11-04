// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// dubna's app_links_platform.h on desktop: an app's own window is a web app
// browser window (out_of_scope_links.h), and its scope is the window
// controller's, which already has the user's rules.

#include <optional>
#include <string>

#include "chrome/browser/app_links/app_links_platform.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/web_applications/app_browser_controller.h"
#include "chrome/browser/ui/web_applications/out_of_scope_links.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/web_contents.h"
#include "url/gurl.h"

namespace app_links {

namespace {

// The controller of the app window that shows `contents`, if any.
web_app::AppBrowserController* Controller(content::WebContents* contents) {
  tabs::TabInterface* tab = tabs::TabInterface::MaybeGetFromContents(contents);
  BrowserWindowInterface* window =
      tab ? tab->GetBrowserWindowInterface() : nullptr;
  return web_app::IsWebAppOwnWindow(window)
             ? web_app::AppBrowserController::From(window)
             : nullptr;
}

}  // namespace

std::optional<std::string> PlatformAppId(content::WebContents* contents) {
  web_app::AppBrowserController* controller = Controller(contents);
  return controller ? std::optional<std::string>(controller->app_id())
                    : std::nullopt;
}

bool PlatformIsUrlInScope(content::WebContents* contents, const GURL& url) {
  web_app::AppBrowserController* controller = Controller(contents);
  return controller && controller->IsUrlInAppScope(url);
}

void OpenInDefaultBrowser(content::WebContents* contents,
                          const GURL& url,
                          bool background) {
  web_app::OpenInDefaultBrowser(
      Profile::FromBrowserContext(contents->GetBrowserContext()), url,
      background);
}

void OnScopeRulesChanged(content::WebContents* contents) {
  if (web_app::AppBrowserController* controller = Controller(contents)) {
    controller->UpdateCustomTabBarVisibility(/*animate=*/false);
  }
}

}  // namespace app_links
