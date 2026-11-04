// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/web_applications/out_of_scope_links.h"

#include <memory>
#include <utility>

#include "base/functional/bind.h"
#include "base/no_destructor.h"
#include "base/process/kill.h"
#include "base/process/launch.h"
#include "base/task/thread_pool.h"
#include "build/build_config.h"
#include "chrome/app/chrome_command_ids.h"
#include "chrome/browser/app_links/app_links.h"
#include "chrome/browser/platform_util.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/shell_integration.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/browser_window/public/profile_browser_collection.h"
#include "chrome/browser/ui/navigator/browser_navigator.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "chrome/browser/ui/web_applications/app_browser_controller.h"
#include "chrome/browser/web_applications/web_app_provider.h"
#include "chrome/browser/web_applications/web_app_registrar.h"
#include "chrome/grit/generated_resources.h"
#include "content/public/browser/web_contents.h"
#include "ui/base/accelerators/menu_label_accelerator_util.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/page_transition_types.h"
#include "ui/menus/simple_menu_model.h"
#include "ui/gfx/text_elider.h"
#include "url/gurl.h"

namespace web_app {

bool IsWebAppOwnWindow(BrowserWindowInterface* window) {
  if (!window || window->GetType() != BrowserWindowInterface::TYPE_APP ||
      !AppBrowserController::IsWebApp(window)) {
    return false;
  }
  AppBrowserController* controller = AppBrowserController::From(window);
  WebAppProvider* provider = WebAppProvider::GetForWebApps(window->GetProfile());
  return controller->AsWebAppBrowserController() &&
         !controller->IsIsolatedWebApp() && provider &&
         provider->registrar_unsafe().GetAppById(controller->app_id());
}

namespace {

#if BUILDFLAG(IS_LINUX)
// Opens an http(s) `url` with xdg-open, as platform_util::OpenExternal's
// fallback does, but without an activation token, so the browser that opens
// it can't take the focus.
void OpenExternalInBackground(const GURL& url) {
  base::LaunchOptions options;
  options.allow_new_privs = true;
  options.environment["XDG_ACTIVATION_TOKEN"] = std::string();
  options.environment["DESKTOP_STARTUP_ID"] = std::string();
  // See platform_util_linux.cc.
  options.environment["MM_NOTTTY"] = "1";
  base::Process process = base::LaunchProcess({"xdg-open", url.spec()}, options);
  if (process.IsValid()) {
    base::EnsureProcessGetsReaped(std::move(process));
  }
}
#endif

// With this build as the default browser: `url` in a tab of the last active
// tabbed window, or a new one. xdg-open would hand it to this process as a
// command line, which always opens a foreground tab and raises the window; a
// `background` tab leaves both as they are.
void OpenInThisBrowser(Profile& profile, const GURL& url, bool background) {
  NavigateParams params(&profile, url, ui::PAGE_TRANSITION_LINK);
  params.browser =
      ProfileBrowserCollection::GetForProfile(&profile)->FindTabbedBrowser();
  params.disposition = background ? WindowOpenDisposition::NEW_BACKGROUND_TAB
                                  : WindowOpenDisposition::NEW_FOREGROUND_TAB;
  using WindowAction = NavigateParams::WindowAction;
  params.window_action = !background ? WindowAction::kShowWindow
                         : params.browser ? WindowAction::kNoAction
                                          : WindowAction::kShowWindowInactive;
  Navigate(&params);
}

// The name of the default browser's desktop entry, from the last lookup;
// empty when it has none.
std::u16string& DefaultBrowserName() {
  static base::NoDestructor<std::u16string> name;
  return *name;
}

// The label of the link context menu item that opens a link in the default
// browser, `background` or not: named after the browser's desktop entry when
// the last lookup found one.
std::u16string DefaultBrowserLinkLabel(bool background) {
  if (DefaultBrowserName().empty()) {
    return l10n_util::GetStringUTF16(
        background ? IDS_CONTENT_CONTEXT_OPENLINKDEFAULTBROWSER_BACKGROUND
                   : IDS_CONTENT_CONTEXT_OPENLINKDEFAULTBROWSER);
  }
  // Short enough that "in background" stays in view, and with its own
  // ampersands, not mnemonics.
  const std::u16string name = ui::EscapeMenuLabelAmpersands(
      gfx::TruncateString(DefaultBrowserName(), 32, gfx::CHARACTER_BREAK));
  return l10n_util::GetStringFUTF16(
      background ? IDS_CONTENT_CONTEXT_OPENLINKNAMEDBROWSER_BACKGROUND
                 : IDS_CONTENT_CONTEXT_OPENLINKNAMEDBROWSER,
      name);
}

}  // namespace

bool MaybeOpenNewContentsOutsideApp(NavigateParams& params) {
  return app_links::MaybeOpenNewContentsOutsideApp(
      params.source_contents, params.url, params.disposition,
      params.post_data != nullptr, params.contents_to_insert.get());
}

void AppendDefaultBrowserLinkItems(const GURL& url,
                                   BrowserWindowInterface* window,
                                   ui::SimpleMenuModel& model,
                                   UpdateMenuItemCallback update_item) {
  if (!url.SchemeIsHTTPOrHTTPS() || !IsWebAppOwnWindow(window)) {
    return;
  }
  static constexpr int kIds[] = {
      IDC_CONTENT_CONTEXT_OPENLINKDEFAULTBROWSER,
      IDC_CONTENT_CONTEXT_OPENLINKDEFAULTBROWSER_BACKGROUND};
  for (int id : kIds) {
    model.AddItem(id, DefaultBrowserLinkLabel(
                          id == IDC_CONTENT_CONTEXT_OPENLINKDEFAULTBROWSER_BACKGROUND));
  }
  // The name again, for the open menu: the https handler's desktop entry.
  base::ThreadPool::PostTaskAndReplyWithResult(
      FROM_HERE, {base::MayBlock(), base::TaskPriority::USER_VISIBLE},
      base::BindOnce([] {
        return shell_integration::GetApplicationNameForScheme(
            GURL("https://example.com/"));
      }),
      base::BindOnce(
          [](UpdateMenuItemCallback update_item, std::u16string name) {
            // Without an entry, Chromium names xdg-open.
            DefaultBrowserName() =
                name == u"xdg-open" ? std::u16string() : name;
            for (int id : kIds) {
              update_item.Run(
                  id, /*enabled=*/true, /*hidden=*/false,
                  DefaultBrowserLinkLabel(
                      id ==
                      IDC_CONTENT_CONTEXT_OPENLINKDEFAULTBROWSER_BACKGROUND));
            }
          },
          std::move(update_item)));
}

void OpenInDefaultBrowser(Profile* profile, const GURL& url, bool background) {
  // Whether this build is the default browser takes xdg-settings, off the UI
  // thread.
  base::ThreadPool::PostTaskAndReplyWithResult(
      FROM_HERE, {base::MayBlock(), base::TaskPriority::USER_BLOCKING},
      base::BindOnce(&shell_integration::GetDefaultBrowser),
      base::BindOnce(
          [](base::WeakPtr<Profile> profile, const GURL& url, bool background,
             shell_integration::DefaultWebClientState state) {
            if (state == shell_integration::IS_DEFAULT && profile) {
              OpenInThisBrowser(*profile, url, background);
              return;
            }
#if BUILDFLAG(IS_LINUX)
            if (background) {
              OpenExternalInBackground(url);
              return;
            }
#endif
            platform_util::OpenExternal(url);
          },
          profile->GetWeakPtr(), url, background));
}

}  // namespace web_app
