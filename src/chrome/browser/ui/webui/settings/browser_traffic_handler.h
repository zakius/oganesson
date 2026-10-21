// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SETTINGS_BROWSER_TRAFFIC_HANDLER_H_
#define CHROME_BROWSER_UI_WEBUI_SETTINGS_BROWSER_TRAFFIC_HANDLER_H_

#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/values.h"
#include "chrome/browser/ui/webui/settings/settings_page_ui_handler.h"
#include "components/prefs/pref_change_registrar.h"

class Profile;

namespace content {
class WebUIDataSource;
}

namespace settings {

// Settings > Privacy and security > Browser traffic, and setup's step of the
// same name: the rows, the presets, the server and its health. The rules are
// dubna's components/browser_traffic; this passes them to the page. Pushes
// "browser-traffic-changed" with the new state.
class BrowserTrafficHandler : public SettingsPageUIHandler {
 public:
  explicit BrowserTrafficHandler(Profile* profile);
  ~BrowserTrafficHandler() override;

  // The page's strings, for a WebUI data source.
  static void AddStrings(content::WebUIDataSource* html_source);

  // SettingsPageUIHandler:
  void RegisterMessages() override;

 private:
  void OnJavascriptAllowed() override;
  void OnJavascriptDisallowed() override;

  void HandleGetState(const base::ListValue& args);
  void HandleSetRow(const base::ListValue& args);
  void HandleApplyPreset(const base::ListValue& args);
  void HandleSetServer(const base::ListValue& args);
  void HandleTestServer(const base::ListValue& args);
  void HandleSetHealthCheck(const base::ListValue& args);
  void HandleUpdateNow(const base::ListValue& args);
  void HandleChoose(const base::ListValue& args);
  void OnServerTested(base::Value callback_id, bool answered);
  void OnChanged();
  base::DictValue State() const;

  raw_ptr<Profile> profile_;
  PrefChangeRegistrar registrar_;
  base::WeakPtrFactory<BrowserTrafficHandler> weak_factory_{this};
};

}  // namespace settings

#endif  // CHROME_BROWSER_UI_WEBUI_SETTINGS_BROWSER_TRAFFIC_HANDLER_H_
