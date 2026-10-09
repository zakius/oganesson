// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/firefox_sync_handler.h"

#include "base/functional/bind.h"
#include "chrome/browser/firefox_sync/firefox_sync_service.h"
#include "chrome/browser/firefox_sync/firefox_sync_service_factory.h"
#include "chrome/browser/profiles/profile.h"
#include "content/public/browser/web_ui.h"

namespace settings {

namespace {

firefox_sync::FirefoxSyncService* Service(Profile* profile) {
  return firefox_sync::FirefoxSyncServiceFactory::GetForProfile(profile);
}

}  // namespace

FirefoxSyncHandler::FirefoxSyncHandler(Profile* profile) : profile_(profile) {}

FirefoxSyncHandler::~FirefoxSyncHandler() = default;

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
