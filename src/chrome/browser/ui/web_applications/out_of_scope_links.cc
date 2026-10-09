// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/web_applications/out_of_scope_links.h"

#include <memory>
#include <utility>

#include "base/functional/bind.h"
#include "base/no_destructor.h"
#include "base/task/thread_pool.h"
#include "build/build_config.h"
#include "chrome/browser/platform_util.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/shell_integration.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "chrome/browser/ui/web_applications/app_browser_controller.h"
#include "chrome/browser/web_applications/web_app_provider.h"
#include "chrome/browser/web_applications/web_app_registrar.h"
#include "chrome/grit/generated_resources.h"
#include "components/prefs/pref_service.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/navigation_handle.h"
#include "content/public/browser/navigation_throttle.h"
#include "content/public/browser/navigation_throttle_registry.h"
#include "content/public/browser/new_window_form_post.h"
#include "ui/base/accelerators/menu_label_accelerator_util.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/page_transition_types.h"
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

bool SendsOutOfScopeLinksOut(BrowserWindowInterface* window) {
  return IsWebAppOwnWindow(window) &&
         window->GetProfile()->GetPrefs()->GetBoolean(
             kOpenOutOfScopeLinksInDefaultBrowser);
}

namespace {

// Whether a link from `window` to `url` leaves the window's web app. The
// app's scope is the one Chromium keeps the window to (manifest scope and
// scope extensions); a user-configured scope belongs there too.
bool LeavesApp(BrowserWindowInterface* window, const GURL& url) {
  return SendsOutOfScopeLinksOut(window) && url.SchemeIsHTTPOrHTTPS() &&
         !AppBrowserController::From(window)->IsUrlInAppScope(url);
}

// The answer of the last default-browser check, so the hooks can decide
// synchronously and leave Chromium's navigation untouched.
bool g_is_default_browser = false;

// The name of the default browser's desktop entry, from the last check; empty
// when it has none or oganesson is the default.
std::u16string& DefaultBrowserName() {
  static base::NoDestructor<std::u16string> name;
  return *name;
}

// The number of the last check started, and of the last one whose answer
// was kept: an answer older than that is dropped.
int g_last_check = 0;
int g_answered_check = 0;

void Answer(int check,
            bool is_default,
            base::OnceClosure done,
            std::u16string name) {
  if (check > g_answered_check) {
    g_answered_check = check;
    g_is_default_browser = is_default;
    // Without an entry, Chromium names xdg-open.
    DefaultBrowserName() = name == u"xdg-open" ? std::u16string() : name;
  }
  if (done) {
    std::move(done).Run();
  }
}

class OutOfScopeLinkThrottle : public content::NavigationThrottle {
 public:
  using content::NavigationThrottle::NavigationThrottle;

  ThrottleCheckResult WillStartRequest() override {
    content::NavigationHandle* handle = navigation_handle();
    tabs::TabInterface* tab =
        tabs::TabInterface::MaybeGetFromContents(handle->GetWebContents());
    if (!tab || !LeavesApp(tab->GetBrowserWindowInterface(), handle->GetURL())) {
      return PROCEED;
    }
    RefreshIsDefaultBrowser();
    // While oganesson is the default browser the link loads in the window,
    // as in Chromium.
    if (IsDefaultBrowser()) {
      return PROCEED;
    }
    platform_util::OpenExternal(handle->GetURL());
    return CANCEL_AND_IGNORE;
  }

  const char* GetNameForLogging() override { return "OutOfScopeLinkThrottle"; }
};

}  // namespace

bool MaybeOpenNewContentsOutsideApp(NavigateParams& params) {
  if (!SendsOutOfScopeLinksOut(params.browser)) {
    return false;
  }
  RefreshIsDefaultBrowser();
  // Popups (window.open with window features) stay: sign-in flows open the
  // provider in one and need its opener. So do form posts, which only
  // Chromium can submit.
  if ((params.disposition != WindowOpenDisposition::NEW_FOREGROUND_TAB &&
       params.disposition != WindowOpenDisposition::NEW_BACKGROUND_TAB &&
       params.disposition != WindowOpenDisposition::NEW_WINDOW) ||
      params.post_data ||
      (params.contents_to_insert &&
       content::IsNewWindowForFormPost(params.contents_to_insert.get())) ||
      IsDefaultBrowser() ||
      !LeavesApp(params.browser, params.url)) {
    return false;
  }
  // A middle click or Ctrl+click leaves the default browser behind the app
  // window, as it leaves a tab in the background.
  OpenInDefaultBrowser(
      params.url,
      params.disposition == WindowOpenDisposition::NEW_BACKGROUND_TAB);
  return true;
}

bool IsDefaultBrowser() {
  return g_is_default_browser;
}

// Called whenever an app window loads a page or opens one, or shows a link's
// context menu, so the answer is current by the time its links are followed.
void RefreshIsDefaultBrowser(base::OnceClosure done) {
  const int check = ++g_last_check;
  base::MakeRefCounted<shell_integration::DefaultBrowserWorker>()
      ->StartCheckIsDefault(base::BindOnce(
          [](int check, base::OnceClosure done,
             shell_integration::DefaultWebClientState state) {
            if (state == shell_integration::IS_DEFAULT) {
              Answer(check, true, std::move(done), std::u16string());
              return;
            }
            // The Name of the https handler's desktop entry.
            base::ThreadPool::PostTaskAndReplyWithResult(
                FROM_HERE, {base::MayBlock(), base::TaskPriority::USER_VISIBLE},
                base::BindOnce([] {
                  return shell_integration::GetApplicationNameForScheme(
                      GURL("https://example.com/"));
                }),
                base::BindOnce(&Answer, check, false, std::move(done)));
          },
          check, std::move(done)));
}

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

bool OpenInDefaultBrowser(const GURL& url, bool background) {
  // xdg-open would hand it back to us.
  if (IsDefaultBrowser()) {
    return false;
  }
#if BUILDFLAG(IS_LINUX)
  if (background) {
    platform_util::OpenExternalInBackground(url);
    return true;
  }
#endif
  platform_util::OpenExternal(url);
  return true;
}

void MaybeAddOutOfScopeLinkThrottle(
    content::NavigationThrottleRegistry& registry) {
  content::NavigationHandle& handle = registry.GetNavigationHandle();
  // Any page an app window loads refreshes the answer, also a restored
  // window's first page, which doesn't go through Navigate().
  if (handle.IsInPrimaryMainFrame()) {
    tabs::TabInterface* tab =
        tabs::TabInterface::MaybeGetFromContents(handle.GetWebContents());
    if (tab && SendsOutOfScopeLinksOut(tab->GetBrowserWindowInterface())) {
      RefreshIsDefaultBrowser();
    }
  }
  // Only the page's own link clicks: not redirects, history, reloads or form
  // posts, and not scripts navigating, even from a click handler (sign-in
  // buttons that fetch the provider's URL and assign it).
  if (!handle.IsInPrimaryMainFrame() || !handle.IsRendererInitiated() ||
      !handle.WasInitiatedByLinkClick() || !handle.HasUserGesture() ||
      handle.IsPost() ||
      handle.GetReloadType() != content::ReloadType::NONE ||
      (handle.GetPageTransition() & ui::PAGE_TRANSITION_FORWARD_BACK)) {
    return;
  }
  registry.AddThrottle(std::make_unique<OutOfScopeLinkThrottle>(registry));
}

}  // namespace web_app
