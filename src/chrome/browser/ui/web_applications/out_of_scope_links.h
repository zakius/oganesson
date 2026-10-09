// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_
#define CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_

#include <string>

#include "base/functional/callback.h"

class BrowserWindowInterface;
class GURL;
struct NavigateParams;

namespace content {
class NavigationThrottleRegistry;
}

namespace web_app {

// Profile pref: links from an installed web app's window that leave the
// app's scope open in the system default browser.
inline constexpr char kOpenOutOfScopeLinksInDefaultBrowser[] =
    "oganesson.web_apps.open_out_of_scope_links_in_default_browser";

// Whether `window` is an installed web app's own window: a registered web app
// that isn't isolated, not a hosted (extension) app. Not its popups (window.open
// with window features): sign-in flows open the provider in one, and its links
// and its opener stay with it. Such a window has no prerendered pages, neither
// its own nor a reparented tab's, whatever the pref: activating one skips the
// navigation throttle, and the pref can be turned on while one is waiting.
bool IsWebAppOwnWindow(BrowserWindowInterface* window);

// Whether `window` is a web app's own window, with the pref on.
bool SendsOutOfScopeLinksOut(BrowserWindowInterface* window);

// For Navigate(): a new tab or window that a web app's window opens on a URL
// out of the app's scope goes to the system default browser, unless that is
// oganesson. Returns true when it took the navigation, which the caller then
// drops.
bool MaybeOpenNewContentsOutsideApp(NavigateParams& params);

// Whether the last default-browser check found oganesson the system default
// browser, which would hand a link given to it back to us. False until a
// check has answered.
bool IsDefaultBrowser();

// Checks again in the background, then runs `done`, after the answer updates
// IsDefaultBrowser() and DefaultBrowserLinkLabel(), or after a newer check's
// answer did.
void RefreshIsDefaultBrowser(base::OnceClosure done = {});

// The label of the link context menu item that opens a link in the system
// default browser, `background` or not: named after the browser's desktop
// entry when the last check found one.
std::u16string DefaultBrowserLinkLabel(bool background);

// Opens `url` in the system default browser; with `background`, without
// letting the browser take focus, where the platform can. Returns false,
// opening nothing, while oganesson is the default browser.
bool OpenInDefaultBrowser(const GURL& url, bool background);

// A link clicked in a web app's window that leaves the app's scope, which
// would load in the window, goes to the system default browser instead.
void MaybeAddOutOfScopeLinkThrottle(
    content::NavigationThrottleRegistry& registry);

}  // namespace web_app

#endif  // CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_
