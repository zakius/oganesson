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
#include "chrome/browser/ui/browser_window/public/profile_browser_collection.h"
#include "chrome/browser/ui/navigator/browser_navigator.h"
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
#include "content/public/browser/navigation_entry.h"
#include "content/public/browser/navigation_handle.h"
#include "content/public/browser/navigation_throttle.h"
#include "content/public/browser/navigation_throttle_registry.h"
#include "content/public/browser/new_window_form_post.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/browser/web_contents.h"
#include "content/public/browser/web_contents_observer.h"
#include "content/public/browser/web_contents_user_data.h"
#include "mojo/public/cpp/bindings/self_owned_receiver.h"
#include "third_party/blink/public/mojom/oganesson/app_link_host.mojom.h"
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

// Whether the user made the scope of `window`'s app strict: every page out
// of it leaves by any route, as an excluded page does.
bool HasStrictScope(BrowserWindowInterface* window) {
  return IsWebAppOwnWindow(window) &&
         IsUserAppScopeStrict(*window->GetProfile()->GetPrefs(),
                              AppBrowserController::From(window)->app_id());
}

// Whether a page of `window` reaching `url` leaves the window's web app: by
// one of the user's exclusions, which no route gets past, or with
// `out_of_scope` or a strict scope, by leaving the app's scope, the one
// Chromium keeps the window to (manifest scope and scope extensions) with the
// user's rules applied.
bool LeavesApp(BrowserWindowInterface* window,
               const GURL& url,
               bool out_of_scope) {
  if (!IsWebAppOwnWindow(window) || !url.SchemeIsHTTPOrHTTPS()) {
    return false;
  }
  AppBrowserController* controller = AppBrowserController::From(window);
  return IsUrlExcludedFromUserAppScope(*window->GetProfile()->GetPrefs(),
                                       controller->app_id(), url) ||
         ((out_of_scope || HasStrictScope(window)) &&
          !controller->IsUrlInAppScope(url));
}

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

// Whether `contents` may open a URL that leaves the app now; see
// ExclusionObserver::MayOpen.
bool MayOpen(content::WebContents* contents);

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
    if (handle->IsPost() ||
        !LeavesApp(tab->GetBrowserWindowInterface(), handle->GetURL(), link)) {
      return PROCEED;
    }
    // A script that keeps trying, or keeps landing on a redirect out, opens
    // one tab per user input, not one per try.
    if (MayOpen(handle->GetWebContents())) {
      OpenInDefaultBrowser(tab->GetBrowserWindowInterface()->GetProfile(),
                           handle->GetURL(),
                           /*background=*/!handle->HasUserGesture());
    }
    return CANCEL_AND_IGNORE;
  }

  const bool link_;
};

// The page's frame asks AppLinkHost before it changes its address, so such
// a change doesn't happen; this is for one the frame didn't ask about, such
// as from a page that moved into the app window while it changed it.
// Same-document navigations (pushState, replaceState, fragments) commit
// without throttles: one that reaches an excluded URL, or from a click one
// out of the app's scope, as a link there would (routers such as Facebook's
// turn link clicks into pushState), opens it outside the app after the fact
// and takes the window back. A pushed entry goes back, as the Back button
// would, to the last entry in the app, so the page's router shows it again;
// for a replaced entry, the page before loads again in its place. The window
// can show the excluded page's content until then. One URL goes out per
// user input: a router that answers the take-back by navigating out again,
// to the same URL or the one it resolves to (Facebook's /share/ links), is
// taken back again without opening another tab in the default browser, a few
// times, so a page that never gives up can't keep the window busy. The
// observer also updates an app window's custom tab bar when the user's scope
// rules change.
class ExclusionObserver
    : public content::WebContentsObserver,
      public content::WebContentsUserData<ExclusionObserver> {
 public:
  void DidGetUserInteraction(const blink::WebInputEvent& event) override {
    take_backs_since_input_ = 0;
    opened_since_input_ = false;
  }

  // Whether a URL that leaves the app may open in the default browser: one
  // per user input, so a page that tries again, or a router that answers
  // with another URL, can't open a tab per try.
  bool MayOpen() {
    return !std::exchange(opened_since_input_, true);
  }

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
    if (!tab) {
      return;
    }
    if (!LeavesApp(tab->GetBrowserWindowInterface(), handle->GetURL(),
                   /*out_of_scope=*/handle->HasUserGesture())) {
      return;
    }
    if (take_backs_since_input_ == kMaxTakeBacksPerInput) {
      return;
    }
    ++take_backs_since_input_;
    if (MayOpen()) {
      OpenInDefaultBrowser(
          Profile::FromBrowserContext(web_contents()->GetBrowserContext()),
          handle->GetURL(), /*background=*/!handle->HasUserGesture());
    }
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

  // Back from `excluded`: with a `replaced` URL, to that URL in its place;
  // otherwise, unless the page is back in the app by now, to the last entry
  // in the app, past every entry the page pushed out of it meanwhile
  // (Facebook pushes a /share/ link and then the URL it resolves to). Both
  // are browser navigations, which the exclusions leave alone.
  static void TakeBack(base::WeakPtr<content::WebContents> contents,
                       const GURL& excluded,
                       const GURL& replaced) {
    tabs::TabInterface* tab =
        contents ? tabs::TabInterface::MaybeGetFromContents(contents.get())
                 : nullptr;
    if (!tab) {
      return;
    }
    BrowserWindowInterface* window = tab->GetBrowserWindowInterface();
    content::NavigationController& controller = contents->GetController();
    if (replaced.is_valid()) {
      if (contents->GetLastCommittedURL() == excluded) {
        content::NavigationController::LoadURLParams params(replaced);
        params.should_replace_current_entry = true;
        params.transition_type = ui::PAGE_TRANSITION_AUTO_TOPLEVEL;
        controller.LoadURLWithParams(params);
      }
      return;
    }
    if (!LeavesApp(window, contents->GetLastCommittedURL(),
                   /*out_of_scope=*/true)) {
      return;
    }
    for (int i = controller.GetLastCommittedEntryIndex() - 1; i >= 0; --i) {
      if (!LeavesApp(window, controller.GetEntryAtIndex(i)->GetURL(),
                     /*out_of_scope=*/true)) {
        controller.GoToIndex(i);
        return;
      }
    }
  }

  PrefChangeRegistrar scope_rules_registrar_;
  static constexpr int kMaxTakeBacksPerInput = 3;
  // Navigations taken back since the user's last input to the page.
  int take_backs_since_input_ = 0;
  bool opened_since_input_ = false;
};

WEB_CONTENTS_USER_DATA_KEY_IMPL(ExclusionObserver);

class AppLinkHost : public blink::mojom::OganessonAppLinkHost {
 public:
  explicit AppLinkHost(content::GlobalRenderFrameHostId frame)
      : frame_(frame) {}

  void OpenOutsideApp(const GURL& url,
                      bool link,
                      bool background,
                      OpenOutsideAppCallback callback) override {
    content::RenderFrameHost* frame =
        content::RenderFrameHost::FromID(frame_);
    content::WebContents* contents =
        frame && frame->IsInPrimaryMainFrame()
            ? content::WebContents::FromRenderFrameHost(frame)
            : nullptr;
    tabs::TabInterface* tab =
        contents ? tabs::TabInterface::MaybeGetFromContents(contents)
                 : nullptr;
    if (!tab || !LeavesApp(tab->GetBrowserWindowInterface(), url, link)) {
      std::move(callback).Run(false);
      return;
    }
    ExclusionObserver::CreateForWebContents(contents);
    if (ExclusionObserver::FromWebContents(contents)->MayOpen()) {
      OpenInDefaultBrowser(tab->GetBrowserWindowInterface()->GetProfile(), url,
                           background);
    }
    std::move(callback).Run(true);
  }

 private:
  const content::GlobalRenderFrameHostId frame_;
};

bool MayOpen(content::WebContents* contents) {
  ExclusionObserver* observer = ExclusionObserver::FromWebContents(contents);
  return !observer || observer->MayOpen();
}

}  // namespace

bool MaybeOpenNewContentsOutsideApp(NavigateParams& params) {
  if (!IsWebAppOwnWindow(params.browser)) {
    return false;
  }
  // Popups (window.open with window features) stay, unless the scope is
  // strict: sign-in flows open the provider in one and need its opener. So do
  // form posts, which only Chromium can submit.
  if ((params.disposition != WindowOpenDisposition::NEW_FOREGROUND_TAB &&
       params.disposition != WindowOpenDisposition::NEW_BACKGROUND_TAB &&
       params.disposition != WindowOpenDisposition::NEW_WINDOW &&
       (params.disposition != WindowOpenDisposition::NEW_POPUP ||
        !HasStrictScope(params.browser))) ||
      params.post_data ||
      (params.contents_to_insert &&
       content::IsNewWindowForFormPost(params.contents_to_insert.get())) ||
      !LeavesApp(params.browser, params.url, /*out_of_scope=*/true)) {
    return false;
  }
  // A middle click or Ctrl+click leaves the default browser behind the app
  // window, as it leaves a tab in the background.
  OpenInDefaultBrowser(
      params.browser->GetProfile(), params.url,
      params.disposition == WindowOpenDisposition::NEW_BACKGROUND_TAB);
  return true;
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

void BindAppLinkHost(
    content::RenderFrameHost* frame,
    mojo::PendingReceiver<blink::mojom::OganessonAppLinkHost> receiver) {
  mojo::MakeSelfOwnedReceiver(
      std::make_unique<AppLinkHost>(frame->GetGlobalId()), std::move(receiver));
}

void MaybeAddOutOfScopeLinkThrottle(
    content::NavigationThrottleRegistry& registry) {
  content::NavigationHandle& handle = registry.GetNavigationHandle();
  // On every tab: one can move into an app window with its page loaded.
  if (handle.IsInPrimaryMainFrame() &&
      tabs::TabInterface::MaybeGetFromContents(handle.GetWebContents())) {
    ExclusionObserver::CreateForWebContents(handle.GetWebContents());
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
  // buttons that fetch the provider's URL and assign it). Exclusions, and
  // with a strict scope every URL out of it, all.
  registry.AddThrottle(std::make_unique<OutOfScopeLinkThrottle>(
      registry, handle.WasInitiatedByLinkClick() && handle.HasUserGesture() &&
                    !handle.IsPost()));
}

}  // namespace web_app
