// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/browser_traffic_handler.h"

#include <optional>
#include <string>

#include "base/functional/bind.h"
#include "chrome/browser/browser_process.h"
#include "chrome/browser/browser_traffic/browser_traffic_monitor.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/search_engines/template_url_service_factory.h"
#include "chrome/grit/generated_resources.h"
#include "components/browser_traffic/browser_traffic.h"
#include "components/prefs/pref_service.h"
#include "components/search_engines/template_url_service.h"
#include "content/public/browser/web_ui.h"
#include "content/public/browser/web_ui_data_source.h"
#include "ui/base/webui/web_ui_util.h"
#include "url/gurl.h"

namespace settings {

namespace {

PrefService& LocalState() {
  return *g_browser_process->local_state();
}

const char* PresetName(browser_traffic::Preset preset) {
  switch (preset) {
    case browser_traffic::Preset::kDirect:
      return "direct";
    case browser_traffic::Preset::kThroughServer:
      return "throughServer";
    case browser_traffic::Preset::kShutIn:
      return "shutIn";
    case browser_traffic::Preset::kCustom:
      return "custom";
  }
}

double JsTime(base::Time time) {
  return time.is_null() ? 0 : time.InMillisecondsFSinceUnixEpoch();
}

const char* BrowserUpdatesName(browser_traffic::BrowserUpdates updates) {
  switch (updates) {
    case browser_traffic::BrowserUpdates::kRow:
      return "row";
    case browser_traffic::BrowserUpdates::kManaged:
      return "managed";
    case browser_traffic::BrowserUpdates::kPackageManager:
      return "packageManager";
  }
}

}  // namespace

BrowserTrafficHandler::BrowserTrafficHandler(Profile* profile)
    : profile_(profile) {}

BrowserTrafficHandler::~BrowserTrafficHandler() = default;

// static
void BrowserTrafficHandler::AddStrings(content::WebUIDataSource* html_source) {
  static constexpr webui::LocalizedString kStrings[] = {
      {"browserTrafficTitle", IDS_BROWSER_TRAFFIC_TITLE},
      {"browserTrafficDescription", IDS_BROWSER_TRAFFIC_DESCRIPTION},
      {"browserTrafficServer", IDS_BROWSER_TRAFFIC_SERVER},
      {"browserTrafficServerDescription",
       IDS_BROWSER_TRAFFIC_SERVER_DESCRIPTION},
      {"browserTrafficServerNotSet", IDS_BROWSER_TRAFFIC_SERVER_NOT_SET},
      {"browserTrafficServerInvalid", IDS_BROWSER_TRAFFIC_SERVER_INVALID},
      {"browserTrafficTest", IDS_BROWSER_TRAFFIC_TEST},
      {"browserTrafficTesting", IDS_BROWSER_TRAFFIC_TESTING},
      {"browserTrafficServerAnswered", IDS_BROWSER_TRAFFIC_SERVER_ANSWERED},
      {"browserTrafficServerNoAnswer", IDS_BROWSER_TRAFFIC_SERVER_NO_ANSWER},
      {"browserTrafficTestToContinue", IDS_BROWSER_TRAFFIC_TEST_TO_CONTINUE},
      {"browserTrafficStatusReachable", IDS_BROWSER_TRAFFIC_STATUS_REACHABLE},
      {"browserTrafficStatusUnreachable",
       IDS_BROWSER_TRAFFIC_STATUS_UNREACHABLE},
      {"browserTrafficStatusNeverAnswered",
       IDS_BROWSER_TRAFFIC_STATUS_NEVER_ANSWERED},
      {"browserTrafficStatusUnchecked", IDS_BROWSER_TRAFFIC_STATUS_UNCHECKED},
      {"browserTrafficServerDownTitle", IDS_BROWSER_TRAFFIC_SERVER_DOWN_TITLE},
      {"browserTrafficServerDown", IDS_BROWSER_TRAFFIC_SERVER_DOWN},
      {"browserTrafficCheckNow", IDS_BROWSER_TRAFFIC_CHECK_NOW},
      {"browserTrafficHealthCheck", IDS_BROWSER_TRAFFIC_HEALTH_CHECK},
      {"browserTrafficHealthCheckDescription",
       IDS_BROWSER_TRAFFIC_HEALTH_CHECK_DESCRIPTION},
      {"browserTrafficPeriodically", IDS_BROWSER_TRAFFIC_PERIODICALLY},
      {"browserTrafficPreset", IDS_BROWSER_TRAFFIC_PRESET},
      {"browserTrafficPresetDirect", IDS_BROWSER_TRAFFIC_PRESET_DIRECT},
      {"browserTrafficPresetDirectDescription",
       IDS_BROWSER_TRAFFIC_PRESET_DIRECT_DESCRIPTION},
      {"browserTrafficPresetThroughServer", IDS_BROWSER_TRAFFIC_PRESET_SERVER},
      {"browserTrafficPresetThroughServerDescription",
       IDS_BROWSER_TRAFFIC_PRESET_SERVER_DESCRIPTION},
      {"browserTrafficPresetShutIn", IDS_BROWSER_TRAFFIC_PRESET_SHUT_IN},
      {"browserTrafficPresetShutInDescription",
       IDS_BROWSER_TRAFFIC_PRESET_SHUT_IN_DESCRIPTION},
      {"browserTrafficPresetCustom", IDS_BROWSER_TRAFFIC_PRESET_CUSTOM},
      {"browserTrafficPresetCustomDescription",
       IDS_BROWSER_TRAFFIC_PRESET_CUSTOM_DESCRIPTION},
      {"browserTrafficWhat", IDS_BROWSER_TRAFFIC_WHAT},
      {"browserTrafficDownload", IDS_BROWSER_TRAFFIC_DOWNLOAD},
      {"browserTrafficRoute", IDS_BROWSER_TRAFFIC_ROUTE},
      {"browserTrafficAutomatic", IDS_BROWSER_TRAFFIC_AUTOMATIC},
      {"browserTrafficOnRequest", IDS_BROWSER_TRAFFIC_ON_REQUEST},
      {"browserTrafficDirect", IDS_BROWSER_TRAFFIC_DIRECT},
      {"browserTrafficProxy", IDS_BROWSER_TRAFFIC_PROXY},
      {"browserTrafficProxyOnly", IDS_BROWSER_TRAFFIC_PROXY_ONLY},
      {"browserTrafficDirectOnly", IDS_BROWSER_TRAFFIC_DIRECT_ONLY},
      {"browserTrafficNoDirectSource", IDS_BROWSER_TRAFFIC_NO_DIRECT_SOURCE},
      {"browserTrafficOffWithoutServer",
       IDS_BROWSER_TRAFFIC_OFF_WITHOUT_SERVER},
      {"browserTrafficServerCantServe", IDS_BROWSER_TRAFFIC_SERVER_CANT_SERVE},
      {"browserTrafficIdle", IDS_BROWSER_TRAFFIC_IDLE},
      {"browserTrafficFrom", IDS_BROWSER_TRAFFIC_FROM},
      {"browserTrafficFromListAuthors", IDS_BROWSER_TRAFFIC_FROM_LIST_AUTHORS},
      {"browserTrafficRow_certificates", IDS_BROWSER_TRAFFIC_CERTIFICATES},
      {"browserTrafficRowDescription_certificates",
       IDS_BROWSER_TRAFFIC_CERTIFICATES_DESCRIPTION},
      {"browserTrafficRow_drm", IDS_BROWSER_TRAFFIC_DRM},
      {"browserTrafficRowDescription_drm", IDS_BROWSER_TRAFFIC_DRM_DESCRIPTION},
      {"browserTrafficRow_extensions", IDS_BROWSER_TRAFFIC_EXTENSIONS},
      {"browserTrafficRowDescription_extensions",
       IDS_BROWSER_TRAFFIC_EXTENSIONS_DESCRIPTION},
      {"browserTrafficRow_content_blocker",
       IDS_BROWSER_TRAFFIC_CONTENT_BLOCKER},
      {"browserTrafficRowDescription_content_blocker",
       IDS_BROWSER_TRAFFIC_CONTENT_BLOCKER_DESCRIPTION},
      {"browserTrafficRow_dictionaries", IDS_BROWSER_TRAFFIC_DICTIONARIES},
      {"browserTrafficRowDescription_dictionaries",
       IDS_BROWSER_TRAFFIC_DICTIONARIES_DESCRIPTION},
      {"browserTrafficRow_bangs", IDS_BROWSER_TRAFFIC_BANGS},
      {"browserTrafficRowDescription_bangs",
       IDS_BROWSER_TRAFFIC_BANGS_DESCRIPTION},
      {"browserTrafficRow_browser_updates",
       IDS_BROWSER_TRAFFIC_BROWSER_UPDATES},
      {"browserTrafficRowDescription_browser_updates",
       IDS_BROWSER_TRAFFIC_BROWSER_UPDATES_DESCRIPTION},
      {"browserTrafficBrowserUpdatesManaged",
       IDS_BROWSER_TRAFFIC_BROWSER_UPDATES_MANAGED},
      {"browserTrafficPackageManager", IDS_BROWSER_TRAFFIC_PACKAGE_MANAGER},
      {"browserTrafficUpdateNow", IDS_BROWSER_TRAFFIC_UPDATE_NOW},
      {"browserTrafficUpdated", IDS_BROWSER_TRAFFIC_UPDATED},
      {"browserTrafficRevocationWarningTitle",
       IDS_BROWSER_TRAFFIC_REVOCATION_WARNING_TITLE},
      {"browserTrafficRevocationWarning",
       IDS_BROWSER_TRAFFIC_REVOCATION_WARNING},
  };
  html_source->AddLocalizedStrings(kStrings);
}

void BrowserTrafficHandler::RegisterMessages() {
  web_ui()->RegisterMessageCallback(
      "getBrowserTraffic",
      base::BindRepeating(&BrowserTrafficHandler::HandleGetState,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "setBrowserTrafficRow",
      base::BindRepeating(&BrowserTrafficHandler::HandleSetRow,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "applyBrowserTrafficPreset",
      base::BindRepeating(&BrowserTrafficHandler::HandleApplyPreset,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "setBrowserTrafficServer",
      base::BindRepeating(&BrowserTrafficHandler::HandleSetServer,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "testBrowserTrafficServer",
      base::BindRepeating(&BrowserTrafficHandler::HandleTestServer,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "setBrowserTrafficHealthCheck",
      base::BindRepeating(&BrowserTrafficHandler::HandleSetHealthCheck,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "updateBrowserTrafficNow",
      base::BindRepeating(&BrowserTrafficHandler::HandleUpdateNow,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "chooseBrowserTraffic",
      base::BindRepeating(&BrowserTrafficHandler::HandleChoose,
                          base::Unretained(this)));
}

void BrowserTrafficHandler::OnJavascriptAllowed() {
  registrar_.Init(&LocalState());
  const auto changed = base::BindRepeating(&BrowserTrafficHandler::OnChanged,
                                           base::Unretained(this));
  browser_traffic::AddObserver(registrar_, changed, changed);
}

void BrowserTrafficHandler::OnJavascriptDisallowed() {
  registrar_.RemoveAll();
  weak_factory_.InvalidateWeakPtrs();
}

void BrowserTrafficHandler::OnChanged() {
  FireWebUIListener("browser-traffic-changed", State());
}

base::DictValue BrowserTrafficHandler::State() const {
  using browser_traffic::Route;
  const PrefService& local_state = LocalState();
  const std::vector<browser_traffic::Row> rows = browser_traffic::ShownRows();
  base::ListValue row_list;
  for (browser_traffic::Row row : rows) {
    row_list.Append(
        base::DictValue()
            .Set("name", browser_traffic::RowName(row))
            .Set("automatic",
                 browser_traffic::GetDownload(local_state, row) ==
                     browser_traffic::Download::kAutomatic)
            .Set("proxy", browser_traffic::GetRoute(local_state, row) ==
                              Route::kProxy)
            .Set("hasDirect", browser_traffic::HasRoute(row, Route::kDirect))
            .Set("hasProxy", browser_traffic::HasRoute(row, Route::kProxy))
            .Set("idle", browser_traffic::IsIdle(local_state, row)));
  }
  const std::optional<GURL> server = browser_traffic::GetServer(local_state);
  return base::DictValue()
      .Set("rows", std::move(row_list))
      .Set("preset",
           PresetName(browser_traffic::GetPreset(local_state, rows)))
      .Set("server", server ? server->spec() : std::string())
      .Set("needsServer", browser_traffic::NeedsServer(local_state, rows))
      .Set("healthPeriodic", browser_traffic::GetHealthCheck(local_state) ==
                                 browser_traffic::HealthCheck::kPeriodically)
      .Set("serverAnswered",
           JsTime(browser_traffic::GetServerAnswered(local_state)))
      .Set("serverFailed",
           JsTime(browser_traffic::GetServerFailed(local_state)))
      .Set("certificatesUpdated",
           JsTime(browser_traffic::GetCertificatesUpdated(local_state)))
      .Set("browserUpdates",
           BrowserUpdatesName(browser_traffic::GetBrowserUpdates()));
}

void BrowserTrafficHandler::HandleGetState(const base::ListValue& args) {
  AllowJavascript();
  ResolveJavascriptCallback(args[0], State());
}

// args: the row's name, whether it is automatic, whether it goes through the
// server.
void BrowserTrafficHandler::HandleSetRow(const base::ListValue& args) {
  const std::optional<browser_traffic::Row> row =
      browser_traffic::RowFromName(args[0].GetString());
  if (!row) {
    return;
  }
  PrefService& local_state = LocalState();
  browser_traffic::SetDownload(local_state, *row,
                               args[1].GetBool()
                                   ? browser_traffic::Download::kAutomatic
                                   : browser_traffic::Download::kOnRequest);
  browser_traffic::SetRoute(local_state, *row,
                            args[2].GetBool()
                                ? browser_traffic::Route::kProxy
                                : browser_traffic::Route::kDirect);
  browser_traffic::SetChosen(local_state);
}

void BrowserTrafficHandler::HandleApplyPreset(const base::ListValue& args) {
  const std::string& name = args[0].GetString();
  for (browser_traffic::Preset preset :
       {browser_traffic::Preset::kDirect,
        browser_traffic::Preset::kThroughServer,
        browser_traffic::Preset::kShutIn}) {
    if (name == PresetName(preset)) {
      browser_traffic::ApplyPreset(LocalState(), preset,
                                   browser_traffic::ShownRows());
      browser_traffic::SetChosen(LocalState());
    }
  }
}

// Saves an address the server may have, or none; resolves whether it saved.
void BrowserTrafficHandler::HandleSetServer(const base::ListValue& args) {
  AllowJavascript();
  const std::string& url = args[1].GetString();
  const std::optional<GURL> server = browser_traffic::ParseServer(url);
  if (server || url.empty()) {
    browser_traffic::SetServer(LocalState(),
                               server ? server->spec() : std::string());
    browser_traffic::SetChosen(LocalState());
  }
  ResolveJavascriptCallback(args[0], base::Value(server || url.empty()));
}

// Resolves whether the address answers, without saving it; with no address,
// asks the saved server.
void BrowserTrafficHandler::HandleTestServer(const base::ListValue& args) {
  AllowJavascript();
  const std::string& url = args[1].GetString();
  const std::optional<GURL> server =
      url.empty() ? browser_traffic::GetServer(LocalState())
                  : browser_traffic::ParseServer(url);
  if (!server) {
    ResolveJavascriptCallback(args[0], base::Value(false));
    return;
  }
  browser_traffic::CheckServer(
      *server, base::BindOnce(&BrowserTrafficHandler::OnServerTested,
                              weak_factory_.GetWeakPtr(), args[0].Clone()));
}

void BrowserTrafficHandler::OnServerTested(base::Value callback_id,
                                           bool answered) {
  ResolveJavascriptCallback(callback_id, base::Value(answered));
}

void BrowserTrafficHandler::HandleSetHealthCheck(const base::ListValue& args) {
  browser_traffic::SetHealthCheck(
      LocalState(), args[0].GetBool()
                        ? browser_traffic::HealthCheck::kPeriodically
                        : browser_traffic::HealthCheck::kOnRequest);
}

void BrowserTrafficHandler::HandleUpdateNow(const base::ListValue& args) {
  const std::optional<browser_traffic::Row> row =
      browser_traffic::RowFromName(args[0].GetString());
  if (row == browser_traffic::Row::kCertificates) {
    browser_traffic::UpdateCertificatesNow();
  } else if (row == browser_traffic::Row::kBangs) {
    if (TemplateURLService* service =
            TemplateURLServiceFactory::GetForProfile(profile_)) {
      service->RefreshBangs();
    }
  }
}

// Setup's Browser traffic step: the rows as they are are the user's choice.
void BrowserTrafficHandler::HandleChoose(const base::ListValue& args) {
  browser_traffic::SetChosen(LocalState());
}

}  // namespace settings
