// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEB_APPLICATIONS_APP_TRAY_H_
#define CHROME_BROWSER_UI_WEB_APPLICATIONS_APP_TRAY_H_

#include "components/webapps/common/web_app_id.h"

class BrowserWindowInterface;
class PrefService;
class Profile;

// An installed web app the user marks to keep running in the tray: closing
// its last window hides the window, and a tray icon brings it back. The
// window's pages keep running, so the app's notifications and messages still
// arrive with every other browser window closed. Quit in the icon's menu
// closes it. See docs/web-apps.md.
namespace web_app {

// Profile pref: per app id, true when the app keeps running in the tray.
inline constexpr char kTrayApps[] = "oganesson.web_apps.tray_apps";

bool IsTrayApp(const PrefService& prefs, const webapps::AppId& app_id);

// Sets it, and adds or removes the tray icon of the app's open windows.
void SetTrayApp(Profile* profile, const webapps::AppId& app_id, bool enabled);

// WebAppBrowserController calls these as an app window opens and closes.
void OnAppWindowCreated(BrowserWindowInterface* browser,
                        const webapps::AppId& app_id);
void OnAppWindowDestroyed(BrowserWindowInterface* browser);

// Hides `browser` instead of closing it, and returns true, if it is the last
// window of a tray app and the close isn't a quit, an uninstall or the
// icon's Quit.
bool MaybeHideToTray(BrowserWindowInterface* browser);

// Shows and activates a tray app's window hidden in the tray, or started
// there at login.
void ShowFromTray(BrowserWindowInterface* browser);

// Whether the app has a badge (navigator.setAppBadge()), which marks its
// tray icon.
void SetAppTrayBadge(Profile* profile,
                     const webapps::AppId& app_id,
                     bool badged);

}  // namespace web_app

#endif  // CHROME_BROWSER_UI_WEB_APPLICATIONS_APP_TRAY_H_
