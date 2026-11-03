// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_BADGING_BADGE_MANAGER_DELEGATE_LINUX_H_
#define CHROME_BROWSER_BADGING_BADGE_MANAGER_DELEGATE_LINUX_H_

#include "chrome/browser/badging/badge_manager_delegate.h"

class Profile;

namespace badging {

class BadgeManager;

// Shows a web app's badge count on its icon in the dock or task manager,
// with the Unity launcher API's D-Bus signal, which KDE Plasma, Dash to Dock,
// Ubuntu Dock and Plank read. The dock matches it to the app's desktop entry.
class BadgeManagerDelegateLinux : public BadgeManagerDelegate {
 public:
  BadgeManagerDelegateLinux(Profile* profile, BadgeManager* badge_manager);

  void OnAppBadgeUpdated(const webapps::AppId& app_id) override;
};

}  // namespace badging

#endif  // CHROME_BROWSER_BADGING_BADGE_MANAGER_DELEGATE_LINUX_H_
