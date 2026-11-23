// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEB_APPLICATIONS_WEB_INSTALL_BADGE_H_
#define CHROME_BROWSER_UI_WEB_APPLICATIONS_WEB_INSTALL_BADGE_H_

class BrowserWindowInterface;

namespace actions {
class ActionInvocationContext;
}

namespace content {
class WebContents;
}

namespace page_actions {
class PageActionController;
}

namespace web_app {

// The address bar's install icon for a site's navigator.install() call
// (chrome/browser/web_applications/web_install_request.h).

// While `web_contents` has a request, shows its tab's install icon with a
// badge, also on a page that isn't installable itself, and returns true.
// Without one, gives the icon its own look back and returns false.
bool ShowWebInstallBadge(page_actions::PageActionController& controller,
                         content::WebContents& web_contents);

// For the install icon's action: when `context` is a click on the icon (not
// the app menu's item) and the active tab has a request, runs it, which opens
// the install dialog an <install> element's click opens, and returns true.
bool RunWebInstallRequest(BrowserWindowInterface* browser,
                          const actions::ActionInvocationContext& context);

}  // namespace web_app

#endif  // CHROME_BROWSER_UI_WEB_APPLICATIONS_WEB_INSTALL_BADGE_H_
