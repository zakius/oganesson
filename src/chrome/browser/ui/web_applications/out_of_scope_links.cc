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
#include "base/task/sequenced_task_runner.h"
#include "base/task/thread_pool.h"
#include "build/build_config.h"
#include "chrome/app/chrome_command_ids.h"
#include "chrome/browser/platform_util.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/shell_integration.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "chrome/browser/ui/web_applications/app_browser_controller.h"
#include "chrome/browser/web_applications/user_app_scope.h"
#include "chrome/browser/web_applications/web_app_provider.h"
#include "chrome/browser/web_applications/web_app_registrar.h"
#include "chrome/grit/generated_resources.h"
#include "components/prefs/pref_change_registrar.h"
#include "components/prefs/pref_service.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/navigation_handle.h"
#include "content/public/browser/navigation_throttle.h"
#include "content/public/browser/navigation_throttle_registry.h"
#include "content/public/browser/new_window_form_post.h"
#include "content/public/browser/page_navigator.h"
#include "content/public/browser/web_contents.h"
#include "content/public/browser/web_contents_observer.h"
#include "content/public/browser/web_contents_user_data.h"
#include "ui/base/accelerators/menu_label_accelerator_util.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/menus/simple_menu_model.h"
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

// Whether a link from `window` to `url` leaves the window's web app. The
// app's scope is the one Chromium keeps the window to (manifest scope and
// scope extensions); a user-configured scope belongs there too.
bool LeavesApp(BrowserWindowInterface* window, const GURL& url) {
  return IsWebAppOwnWindow(window) && url.SchemeIsHTTPOrHTTPS() &&
         !AppBrowserController::From(window)->IsUrlInAppScope(url);
}

// Whether a page of `window` reaching `url` leaves the window's web app by
// one of the user's exclusions, which no route gets past: not script
// navigations, redirects or same-document navigations either.
bool HitsExclusion(BrowserWindowInterface* window, const GURL& url) {
  return IsWebAppOwnWindow(window) && url.SchemeIsHTTPOrHTTPS() &&
         IsUrlExcludedFromUserAppScope(
             *window->GetProfile()->GetPrefs(),
             AppBrowserController::From(window)->app_id(), url);
}

// Opens `url`, excluded from the app of `contents`' window, in the default
// browser; while that is oganesson, in a regular tab, as a target=_blank link
// opens. Without a user gesture, the default browser stays behind the app
// window.
void OpenExcludedUrl(content::WebContents* contents,
                     const GURL& url,
                     bool user_gesture) {
  RefreshIsDefaultBrowser();
  if (OpenInDefaultBrowser(url, /*background=*/!user_gesture)) {
    return;
  }
  // Not from inside the navigation that reached it. Not as a link either, which
  // navigation capturing would take back into an app window.
  base::SequencedTaskRunner::GetCurrentDefault()->PostTask(
      FROM_HERE, base::BindOnce(
                     [](base::WeakPtr<content::WebContents> contents,
                        const GURL& url) {
                       if (contents) {
                         contents->OpenURL(
                             content::OpenURLParams(
                                 url, content::Referrer(),
                                 WindowOpenDisposition::NEW_FOREGROUND_TAB,
                                 ui::PAGE_TRANSITION_AUTO_TOPLEVEL, false),
                             {});
                       }
                     },
                     contents->GetWeakPtr(), url));
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
  // `link`: the page's own link click, which also leaves the app for being
  // out of its scope; any other navigation only for an exclusion.
  OutOfScopeLinkThrottle(content::NavigationThrottleRegistry& registry,
                         bool link)
      : content::NavigationThrottle(registry), link_(link) {}

  ThrottleCheckResult WillStartRequest() override { return Check(link_); }

  // Every hop, the last one included; a link redirected in scope stays.
  ThrottleCheckResult WillRedirectRequest() override { return Check(false); }

  const char* GetNameForLogging() override { return "OutOfScopeLinkThrottle"; }

 private:
  ThrottleCheckResult Check(bool link) {
    content::NavigationHandle* handle = navigation_handle();
    tabs::TabInterface* tab =
        tabs::TabInterface::MaybeGetFromContents(handle->GetWebContents());
    if (!tab) {
      return PROCEED;
    }
    // A post's body can't go along; a 302 or 303 after it is a GET again.
    if (!handle->IsPost() &&
        HitsExclusion(tab->GetBrowserWindowInterface(), handle->GetURL())) {
      OpenExcludedUrl(handle->GetWebContents(), handle->GetURL(),
                      handle->HasUserGesture());
      return CANCEL_AND_IGNORE;
    }
    if (!link || !LeavesApp(tab->GetBrowserWindowInterface(), handle->GetURL())) {
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

  const bool link_;
};

// Same-document navigations (pushState, replaceState, fragments) commit
// without throttles: one that reaches an excluded URL opens it outside the
// app after the fact and takes the window back. A pushed entry goes back, as
// the Back button would, so the page's router shows the page before again;
// for a replaced entry, the page before loads again in its place. The window
// can show the excluded page's content until then. The observer also updates
// an app window's custom tab bar when the user's scope rules change.
class ExclusionObserver
    : public content::WebContentsObserver,
      public content::WebContentsUserData<ExclusionObserver> {
 public:
  void DidFinishNavigation(content::NavigationHandle* handle) override {
    // Not history navigations: a Back or Forward that loops between two
    // excluded entries would never end.
    if (!handle->IsInPrimaryMainFrame() || !handle->IsSameDocument() ||
        !handle->HasCommitted() || !handle->IsRendererInitiated() ||
        handle->IsHistory()) {
      return;
    }
    tabs::TabInterface* tab =
        tabs::TabInterface::MaybeGetFromContents(web_contents());
    if (!tab || !HitsExclusion(tab->GetBrowserWindowInterface(),
                               handle->GetURL())) {
      return;
    }
    OpenExcludedUrl(web_contents(), handle->GetURL(), handle->HasUserGesture());
    base::SequencedTaskRunner::GetCurrentDefault()->PostTask(
        FROM_HERE,
        base::BindOnce(&TakeBack, web_contents()->GetWeakPtr(),
                       handle->GetURL(),
                       handle->DidReplaceEntry()
                           ? handle->GetPreviousPrimaryMainFrameURL()
                           : GURL()));
  }

 private:
  explicit ExclusionObserver(content::WebContents* contents)
      : content::WebContentsObserver(contents),
        content::WebContentsUserData<ExclusionObserver>(*contents) {
    scope_rules_registrar_.Init(
        Profile::FromBrowserContext(contents->GetBrowserContext())
            ->GetPrefs());
    scope_rules_registrar_.Add(
        kUserAppScopeRules,
        base::BindRepeating(&ExclusionObserver::OnScopeRulesChanged,
                            base::Unretained(this)));
  }
  friend class content::WebContentsUserData<ExclusionObserver>;
  WEB_CONTENTS_USER_DATA_KEY_DECL();

  // The scope rules decide where an app window shows its custom tab bar, the
  // one with the page's origin that out-of-scope pages get.
  void OnScopeRulesChanged() {
    tabs::TabInterface* tab =
        tabs::TabInterface::MaybeGetFromContents(web_contents());
    BrowserWindowInterface* window =
        tab ? tab->GetBrowserWindowInterface() : nullptr;
    if (AppBrowserController* controller =
            window ? AppBrowserController::From(window) : nullptr) {
      controller->UpdateCustomTabBarVisibility(/*animate=*/false);
    }
  }

  // Back from `excluded` unless the page moved on: to the entry before it, or
  // with a `replaced` URL, to that URL in its place. Both are browser
  // navigations, which the exclusions leave alone.
  static void TakeBack(base::WeakPtr<content::WebContents> contents,
                       const GURL& excluded,
                       const GURL& replaced) {
    if (!contents || contents->GetLastCommittedURL() != excluded) {
      return;
    }
    content::NavigationController& controller = contents->GetController();
    if (replaced.is_empty() && controller.CanGoBack()) {
      controller.GoBack();
    } else if (replaced.is_valid()) {
      content::NavigationController::LoadURLParams params(replaced);
      params.should_replace_current_entry = true;
      params.transition_type = ui::PAGE_TRANSITION_AUTO_TOPLEVEL;
      controller.LoadURLWithParams(params);
    }
  }

  PrefChangeRegistrar scope_rules_registrar_;
};

WEB_CONTENTS_USER_DATA_KEY_IMPL(ExclusionObserver);

}  // namespace

bool MaybeOpenNewContentsOutsideApp(NavigateParams& params) {
  if (!IsWebAppOwnWindow(params.browser)) {
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
    model.SetVisibleAt(model.GetItemCount() - 1, !IsDefaultBrowser());
  }
  RefreshIsDefaultBrowser(base::BindOnce(
      [](UpdateMenuItemCallback update_item) {
        for (int id : kIds) {
          update_item.Run(
              id, /*enabled=*/true, /*hidden=*/IsDefaultBrowser(),
              DefaultBrowserLinkLabel(
                  id == IDC_CONTENT_CONTEXT_OPENLINKDEFAULTBROWSER_BACKGROUND));
        }
      },
      std::move(update_item)));
}

bool OpenInDefaultBrowser(const GURL& url, bool background) {
  // xdg-open would hand it back to us.
  if (IsDefaultBrowser()) {
    return false;
  }
#if BUILDFLAG(IS_LINUX)
  if (background) {
    OpenExternalInBackground(url);
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
    if (tab && IsWebAppOwnWindow(tab->GetBrowserWindowInterface())) {
      RefreshIsDefaultBrowser();
    }
    // On every tab: one can move into an app window with its page loaded.
    if (tab) {
      ExclusionObserver::CreateForWebContents(handle.GetWebContents());
    }
  }
  // Only the page's navigations: not history or reloads, nor the app's
  // launch.
  if (!handle.IsInPrimaryMainFrame() || !handle.IsRendererInitiated() ||
      handle.GetReloadType() != content::ReloadType::NONE ||
      (handle.GetPageTransition() & ui::PAGE_TRANSITION_FORWARD_BACK)) {
    return;
  }
  // Out of scope, only the page's own link clicks: not redirects or form
  // posts, and not scripts navigating, even from a click handler (sign-in
  // buttons that fetch the provider's URL and assign it). Exclusions, all.
  registry.AddThrottle(std::make_unique<OutOfScopeLinkThrottle>(
      registry, handle.WasInitiatedByLinkClick() && handle.HasUserGesture() &&
                    !handle.IsPost()));
}

}  // namespace web_app
