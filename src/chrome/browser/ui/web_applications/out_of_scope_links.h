// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_
#define CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_

#include <string>

#include "base/functional/callback.h"
#include "mojo/public/cpp/bindings/pending_receiver.h"
#include "third_party/blink/public/mojom/oganesson/app_link_host.mojom.h"

class BrowserWindowInterface;
class GURL;
struct NavigateParams;

namespace ui {
class SimpleMenuModel;
}

namespace content {
class NavigationThrottleRegistry;
class RenderFrameHost;
}

namespace web_app {

// Whether `window` is an installed web app's own window: a registered web app
// that isn't isolated, not a hosted (extension) app. Not its popups (window.open
// with window features): sign-in flows open the provider in one, and its links
// and its opener stay with it. Such a window has no prerendered pages, neither
// its own nor a reparented tab's: activating one skips the navigation
// throttle. Links from such a window that leave the app's scope open in the
// system default browser.
bool IsWebAppOwnWindow(BrowserWindowInterface* window);

// For Navigate(): a new tab or window that a web app's window opens on a URL
// out of the app's scope goes to the system default browser; with a strict
// scope, so does a popup. Returns true
// when it took the navigation, which the caller then drops.
bool MaybeOpenNewContentsOutsideApp(NavigateParams& params);

// The link context menu's update of one item: (command id, enabled, hidden,
// label), as RenderViewContextMenuBase::UpdateMenuItem.
using UpdateMenuItemCallback =
    base::RepeatingCallback<void(int, bool, bool, const std::u16string&)>;

// Adds "Open link in default browser" and its background twin to `model` for
// an http(s) `url` in a `window` that sends out-of-scope links out, labeled
// from the last lookup of the browser's name; `update_item` relabels them in
// the open menu after the next.
void AppendDefaultBrowserLinkItems(const GURL& url,
                                   BrowserWindowInterface* window,
                                   ui::SimpleMenuModel& model,
                                   UpdateMenuItemCallback update_item);

// Opens `url` in the system default browser, whichever it is: oganesson opens
// it in a browser window. With `background`, without letting the browser take
// focus, where the platform can.
void OpenInDefaultBrowser(const GURL& url, bool background);

// A link clicked in a web app's window that leaves the app's scope, which
// would load in the window, goes to the system default browser instead; so
// does a same-document navigation from a click that leaves it. So does any
// URL the page reaches that one of the user's exclusions matches, or with a
// strict scope, any URL out of the scope: also by script or redirect. The
// window undoes a same-document navigation.
void MaybeAddOutOfScopeLinkThrottle(
    content::NavigationThrottleRegistry& registry);

// Binds the host that a main frame in a web app's window asks, before its page
// changes its address (navigates, pushState, replaceState, hash), whether
// the URL leaves the app; if it does, the address doesn't change, and the
// host opens the URL in the system default browser, once per user input
// (third_party/blink/renderer/core/html/oganesson_app_links.h).
void BindAppLinkHost(
    content::RenderFrameHost* frame,
    mojo::PendingReceiver<blink::mojom::OganessonAppLinkHost> receiver);

}  // namespace web_app

#endif  // CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_
