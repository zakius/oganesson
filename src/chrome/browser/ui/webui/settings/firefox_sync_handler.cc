// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/firefox_sync_handler.h"

#include "base/functional/bind.h"
#include "chrome/browser/firefox_sync/firefox_sync_service.h"
#include "chrome/browser/firefox_sync/firefox_sync_service_factory.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/grit/generated_resources.h"
#include "content/public/browser/web_ui.h"
#include "content/public/browser/web_ui_data_source.h"
#include "ui/base/webui/web_ui_util.h"

namespace settings {

namespace {

firefox_sync::FirefoxSyncService* Service(Profile* profile) {
  return firefox_sync::FirefoxSyncServiceFactory::GetForProfile(profile);
}

}  // namespace

FirefoxSyncHandler::FirefoxSyncHandler(Profile* profile) : profile_(profile) {}

FirefoxSyncHandler::~FirefoxSyncHandler() = default;

// static
void FirefoxSyncHandler::AddStrings(content::WebUIDataSource* html_source) {
  static constexpr webui::LocalizedString kStrings[] = {
      {"firefoxSyncSectionTitle", IDS_FIREFOX_SYNC_SECTION_TITLE},
      {"firefoxSyncTitle", IDS_FIREFOX_SYNC_TITLE},
      {"firefoxSyncSignedInAs", IDS_FIREFOX_SYNC_SIGNED_IN_AS},
      {"firefoxSyncSignInDescription", IDS_FIREFOX_SYNC_SIGN_IN_DESCRIPTION},
      {"firefoxSyncNeedsServer", IDS_FIREFOX_SYNC_NEEDS_SERVER},
      {"firefoxSyncSyncing", IDS_FIREFOX_SYNC_SYNCING},
      {"firefoxSyncNotSynced", IDS_FIREFOX_SYNC_NOT_SYNCED},
      {"firefoxSyncLastSynced", IDS_FIREFOX_SYNC_LAST_SYNCED},
      {"firefoxSyncSignIn", IDS_FIREFOX_SYNC_SIGN_IN},
      {"firefoxSyncSyncNow", IDS_FIREFOX_SYNC_SYNC_NOW},
      {"firefoxSyncSignOut", IDS_FIREFOX_SYNC_SIGN_OUT},
      {"firefoxSyncAccountServer", IDS_FIREFOX_SYNC_ACCOUNT_SERVER},
      {"firefoxSyncUseMozilla", IDS_FIREFOX_SYNC_USE_MOZILLA},
      {"firefoxSyncStorageServer", IDS_FIREFOX_SYNC_STORAGE_SERVER},
      {"firefoxSyncStorageServerDefault",
       IDS_FIREFOX_SYNC_STORAGE_SERVER_DEFAULT},
      {"firefoxSyncNotSupported", IDS_FIREFOX_SYNC_NOT_SUPPORTED},
      {"firefoxSyncHistoryNotSaved", IDS_FIREFOX_SYNC_HISTORY_NOT_SAVED},
      {"firefoxSyncCount", IDS_FIREFOX_SYNC_COUNT},
      {"firefoxSyncRemoteTabs", IDS_FIREFOX_SYNC_REMOTE_TABS},
      {"firefoxSyncRemoteTabsEmpty", IDS_FIREFOX_SYNC_REMOTE_TABS_EMPTY},
  };
  html_source->AddLocalizedStrings(kStrings);
}

void FirefoxSyncHandler::RegisterMessages() {
  web_ui()->RegisterMessageCallback(
      "getFirefoxSyncStatus",
      base::BindRepeating(&FirefoxSyncHandler::HandleGetStatus,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "firefoxSyncSignIn", base::BindRepeating(&FirefoxSyncHandler::HandleSignIn,
                                               base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "firefoxSyncSignOut",
      base::BindRepeating(&FirefoxSyncHandler::HandleSignOut,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "setFirefoxSyncServer",
      base::BindRepeating(&FirefoxSyncHandler::HandleSetServer,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "setFirefoxSyncType",
      base::BindRepeating(&FirefoxSyncHandler::HandleSetType,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "firefoxSyncNow", base::BindRepeating(&FirefoxSyncHandler::HandleSyncNow,
                                            base::Unretained(this)));
}

void FirefoxSyncHandler::OnJavascriptAllowed() {
  if (auto* service = Service(profile_)) {
    subscription_ = service->AddStatusObserver(base::BindRepeating(
        &FirefoxSyncHandler::OnStatusChanged, base::Unretained(this)));
  }
}

void FirefoxSyncHandler::OnJavascriptDisallowed() {
  subscription_ = {};
}

void FirefoxSyncHandler::OnStatusChanged() {
  FireWebUIListener("firefox-sync-status-changed", Status());
}

base::DictValue FirefoxSyncHandler::Status() const {
  auto* service = Service(profile_);
  base::DictValue status =
      service ? service->GetStatus() : base::DictValue();
  status.Set("available", service != nullptr);
  return status;
}

void FirefoxSyncHandler::HandleGetStatus(const base::ListValue& args) {
  AllowJavascript();
  ResolveJavascriptCallback(args[0], Status());
}

void FirefoxSyncHandler::HandleSignIn(const base::ListValue& args) {
  if (auto* service = Service(profile_)) {
    service->SignIn();
  }
}

void FirefoxSyncHandler::HandleSignOut(const base::ListValue& args) {
  if (auto* service = Service(profile_)) {
    service->SignOut();
  }
}

// [server, syncStorage]: the accounts server, or the sync server.
void FirefoxSyncHandler::HandleSetServer(const base::ListValue& args) {
  auto* service = Service(profile_);
  if (service && args.size() == 2 && args[0].is_string() &&
      args[1].is_bool()) {
    service->SetServer(args[0].GetString(), args[1].GetBool());
  }
}

// [name, enabled]
void FirefoxSyncHandler::HandleSetType(const base::ListValue& args) {
  auto* service = Service(profile_);
  if (service && args.size() == 2 && args[0].is_string() &&
      args[1].is_bool()) {
    service->SetTypeEnabled(args[0].GetString(), args[1].GetBool());
  }
}

void FirefoxSyncHandler::HandleSyncNow(const base::ListValue& args) {
  if (auto* service = Service(profile_)) {
    service->SyncNow();
  }
}

}  // namespace settings
