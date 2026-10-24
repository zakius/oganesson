// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SETTINGS_FIREFOX_SYNC_HANDLER_H_
#define CHROME_BROWSER_UI_WEBUI_SETTINGS_FIREFOX_SYNC_HANDLER_H_

#include "base/callback_list.h"
#include "base/memory/raw_ptr.h"
#include "base/values.h"
#include "chrome/browser/ui/webui/settings/settings_page_ui_handler.h"

class Profile;

namespace content {
class WebUIDataSource;
}

namespace settings {

// The Firefox Sync section, Settings -> Sync: status, sign in and
// out, the sync server, sync now, and a switch per data type. Pushes "firefox-sync-status-changed" with the new status.
class FirefoxSyncHandler : public SettingsPageUIHandler {
 public:
  explicit FirefoxSyncHandler(Profile* profile);
  ~FirefoxSyncHandler() override;

  // The section's strings, for settings' data source.
  static void AddStrings(content::WebUIDataSource* html_source);

  // SettingsPageUIHandler:
  void RegisterMessages() override;

 private:
  void OnJavascriptAllowed() override;
  void OnJavascriptDisallowed() override;

  void HandleGetStatus(const base::ListValue& args);
  void HandleSignIn(const base::ListValue& args);
  void HandleSignOut(const base::ListValue& args);
  void HandleSetServer(const base::ListValue& args);
  void HandleSetType(const base::ListValue& args);
  void HandleSetInstantTabs(const base::ListValue& args);
  void HandleSetReceiveInterval(const base::ListValue& args);
  void HandleSyncNow(const base::ListValue& args);
  void OnStatusChanged();
  base::DictValue Status() const;

  raw_ptr<Profile> profile_;
  base::CallbackListSubscription subscription_;
};

}  // namespace settings

#endif  // CHROME_BROWSER_UI_WEBUI_SETTINGS_FIREFOX_SYNC_HANDLER_H_
