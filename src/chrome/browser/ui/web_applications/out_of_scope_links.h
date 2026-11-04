// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_
#define CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_

#include <string>

#include "base/functional/callback.h"

class BrowserWindowInterface;
class GURL;
class Profile;
struct NavigateParams;

namespace ui {
class SimpleMenuModel;
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

// For Navigate(): dubna's app_links::MaybeOpenNewContentsOutsideApp for the
// new tab, window or popup of `params`. Returns true when it took the
// navigation, which the caller then drops.
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

// Opens `url` in the system default browser, whichever it is. If that is this
// build, in a tab of `profile`'s last active tabbed window. With `background`,
// without letting the browser take focus, where the platform can, and here as
// a background tab.
void OpenInDefaultBrowser(Profile* profile, const GURL& url, bool background);

}  // namespace web_app

#endif  // CHROME_BROWSER_UI_WEB_APPLICATIONS_OUT_OF_SCOPE_LINKS_H_
