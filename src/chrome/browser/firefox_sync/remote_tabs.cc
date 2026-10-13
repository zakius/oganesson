// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/firefox_sync/remote_tabs.h"

#include <algorithm>
#include <utility>

#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/sync/session_sync_service_factory.h"
#include "components/sessions/core/session_id.h"
#include "components/sessions/core/session_types.h"
#include "components/sync/protocol/session_specifics.pb.h"
#include "components/sync_device_info/device_info.h"
#include "components/sync_sessions/session_sync_service.h"
#include "components/sync_sessions/synced_session.h"

namespace firefox_sync {

namespace {

using syncer::DeviceInfo;

// The device's only window. Tab ids count from 1 within each device: a
// session tag and a tab id together name a tab.
constexpr int kWindowId = 1;

base::Time FromMillis(double ms) {
  return base::Time::FromMillisecondsSinceUnixEpoch(ms);
}

std::unique_ptr<sync_sessions::SyncedSession> ToSession(
    const base::DictValue& device) {
  const std::string* id = device.FindString("id");
  const base::ListValue* tabs = device.FindList("tabs");
  if (!id || id->empty() || !tabs) {
    return nullptr;
  }
  auto session = std::make_unique<sync_sessions::SyncedSession>();
  session->SetSessionTag(*id);
  const std::string* name = device.FindString("name");
  session->SetSessionName(name ? *name : std::string());
  base::Time modified = FromMillis(device.FindDouble("modified").value_or(0));
  session->SetModifiedTime(modified);
  const std::string* type = device.FindString("type");
  std::string kind = type ? *type : std::string();
  if (kind == "phone") {
    session->SetDeviceTypeAndFormFactor(DeviceInfo::DeviceType::kPhone,
                                        DeviceInfo::FormFactor::kPhone);
  } else if (kind == "tablet") {
    session->SetDeviceTypeAndFormFactor(DeviceInfo::DeviceType::kTablet,
                                        DeviceInfo::FormFactor::kTablet);
  } else if (kind == "desktop") {
    session->SetDeviceTypeAndFormFactor(DeviceInfo::DeviceType::kOther,
                                        DeviceInfo::FormFactor::kDesktop);
  }

  auto window = std::make_unique<sync_sessions::SyncedSessionWindow>();
  SessionID window_id = SessionID::FromSerializedValue(kWindowId);
  window->wrapped_window.window_id = window_id;
  window->wrapped_window.timestamp = modified;
  int next_id = 1;
  for (const base::Value& value : *tabs) {
    const base::DictValue* tab = value.GetIfDict();
    const std::string* url = tab ? tab->FindString("url") : nullptr;
    if (!url) {
      continue;
    }
    sync_pb::SessionTab data;
    data.set_window_id(kWindowId);
    data.set_tab_id(next_id++);
    data.set_tab_visual_index(window->wrapped_window.tabs.size());
    data.set_current_navigation_index(0);
    double last_used = tab->FindDouble("lastUsed").value_or(0);
    data.set_last_active_time_unix_epoch_millis(last_used);
    sync_pb::TabNavigation* navigation = data.add_navigation();
    navigation->set_virtual_url(*url);
    if (const std::string* title = tab->FindString("title")) {
      navigation->set_title(*title);
    }
    if (const std::string* icon = tab->FindString("icon")) {
      navigation->set_favicon_url(*icon);
    }
    auto session_tab = std::make_unique<sessions::SessionTab>();
    // The tab's time is when it was last used, as Firefox shows it.
    sync_sessions::SetSessionTabFromSyncData(data, FromMillis(last_used),
                                             session_tab.get());
    window->wrapped_window.tabs.push_back(std::move(session_tab));
  }
  if (window->wrapped_window.tabs.empty()) {
    return nullptr;
  }
  session->windows[window_id] = std::move(window);
  return session;
}

}  // namespace

RemoteTabs::RemoteTabs(Profile* profile) : profile_(profile) {}

RemoteTabs::~RemoteTabs() = default;

void RemoteTabs::Update(const base::ListValue& devices) {
  sessions_.clear();
  for (const base::Value& device : devices) {
    if (const base::DictValue* dict = device.GetIfDict()) {
      if (auto session = ToSession(*dict)) {
        sessions_.push_back(std::move(session));
      }
    }
  }
  std::ranges::stable_sort(sessions_, std::ranges::greater(),
                           [](const auto& session) {
                             return session->GetModifiedTime();
                           });
  Publish(true);
}

void RemoteTabs::Clear() {
  sessions_.clear();
  Publish(false);
}

void RemoteTabs::Publish(bool active) {
  sync_sessions::SessionSyncService* service =
      SessionSyncServiceFactory::GetForProfile(profile_);
  if (service) {
    service->SetExternalOpenTabsUIDelegate(active ? this : nullptr);
  }
}

const sync_sessions::SyncedSession* RemoteTabs::Find(
    const std::string& tag) const {
  auto it = std::ranges::find(sessions_, tag, [](const auto& session) {
    return session->GetSessionTag();
  });
  return it == sessions_.end() ? nullptr : it->get();
}

bool RemoteTabs::GetAllForeignSessions(
    std::vector<raw_ptr<const sync_sessions::SyncedSession,
                        VectorExperimental>>* sessions) {
  sessions->clear();
  for (const auto& session : sessions_) {
    sessions->push_back(session.get());
  }
  return !sessions->empty();
}

base::flat_map<std::string, base::Time>
RemoteTabs::GetAllForeignSessionLastModifiedTimes() const {
  base::flat_map<std::string, base::Time> times;
  for (const auto& session : sessions_) {
    times[session->GetSessionTag()] = session->GetModifiedTime();
  }
  return times;
}

bool RemoteTabs::GetForeignTab(const std::string& tag,
                               SessionID tab_id,
                               const sessions::SessionTab** tab) {
  const sync_sessions::SyncedSession* session = Find(tag);
  if (!session) {
    return false;
  }
  for (const auto& [id, window] : session->windows) {
    for (const auto& session_tab : window->wrapped_window.tabs) {
      if (session_tab->tab_id == tab_id) {
        *tab = session_tab.get();
        return true;
      }
    }
  }
  return false;
}

void RemoteTabs::DeleteForeignSession(const std::string& tag) {
  // Firefox Sync can't delete another device's tabs; this hides them until
  // the next sync brings them back, if that device still uploads any.
  std::erase_if(sessions_, [&](const auto& session) {
    return session->GetSessionTag() == tag;
  });
  Publish(true);
}

std::vector<const sessions::SessionWindow*> RemoteTabs::GetForeignSession(
    const std::string& tag) {
  std::vector<const sessions::SessionWindow*> windows;
  if (const sync_sessions::SyncedSession* session = Find(tag)) {
    for (const auto& [id, window] : session->windows) {
      windows.push_back(&window->wrapped_window);
    }
  }
  return windows;
}

bool RemoteTabs::GetForeignSessionTabs(
    const std::string& tag,
    std::vector<const sessions::SessionTab*>* tabs) {
  const sync_sessions::SyncedSession* session = Find(tag);
  if (!session) {
    return false;
  }
  tabs->clear();
  for (const auto& [id, window] : session->windows) {
    for (const auto& tab : window->wrapped_window.tabs) {
      tabs->push_back(tab.get());
    }
  }
  std::ranges::stable_sort(*tabs, std::ranges::greater(),
                           [](const sessions::SessionTab* tab) {
                             return tab->timestamp;
                           });
  return true;
}

bool RemoteTabs::GetLocalSession(const sync_sessions::SyncedSession** local) {
  return false;
}

}  // namespace firefox_sync
