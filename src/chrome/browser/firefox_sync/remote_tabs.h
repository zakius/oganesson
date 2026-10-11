// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_FIREFOX_SYNC_REMOTE_TABS_H_
#define CHROME_BROWSER_FIREFOX_SYNC_REMOTE_TABS_H_

#include <memory>
#include <string>
#include <vector>

#include "base/memory/raw_ptr.h"
#include "base/values.h"
#include "components/sync_sessions/open_tabs_ui_delegate.h"

class Profile;

namespace sync_sessions {
struct SyncedSession;
}

namespace firefox_sync {

// The other devices' open tabs from Firefox Sync, as Chromium's synced
// sessions: History's "Tabs from other devices", the app menu's Recent tabs
// and the tabs extension API read them through the SessionSyncService, which
// returns this delegate while it is set. One window per device, one
// navigation per tab (its current URL).
class RemoteTabs : public sync_sessions::OpenTabsUIDelegate {
 public:
  explicit RemoteTabs(Profile* profile);
  ~RemoteTabs() override;

  // `devices` is the tabs engine's result: [{id, name, type, modified (ms),
  // tabs: [{url, title, icon, lastUsed (ms)}]}]. Shows them and notifies the
  // views; an empty list still counts as tab sync being on.
  void Update(const base::ListValue& devices);
  // Hands the views back to Chromium's own sessions (signed out, or tabs
  // turned off). Call it before destroying this, while the SessionSyncService
  // still exists.
  void Clear();

  // sync_sessions::OpenTabsUIDelegate:
  bool GetAllForeignSessions(
      std::vector<raw_ptr<const sync_sessions::SyncedSession,
                          VectorExperimental>>* sessions) override;
  base::flat_map<std::string, base::Time>
  GetAllForeignSessionLastModifiedTimes() const override;
  bool GetForeignTab(const std::string& tag,
                     SessionID tab_id,
                     const sessions::SessionTab** tab) override;
  void DeleteForeignSession(const std::string& tag) override;
  std::vector<const sessions::SessionWindow*> GetForeignSession(
      const std::string& tag) override;
  bool GetForeignSessionTabs(
      const std::string& tag,
      std::vector<const sessions::SessionTab*>* tabs) override;
  bool GetLocalSession(const sync_sessions::SyncedSession** local) override;

 private:
  const sync_sessions::SyncedSession* Find(const std::string& tag) const;
  void Publish(bool active);

  const raw_ptr<Profile> profile_;
  // Most recently modified first.
  std::vector<std::unique_ptr<sync_sessions::SyncedSession>> sessions_;
};

}  // namespace firefox_sync

#endif  // CHROME_BROWSER_FIREFOX_SYNC_REMOTE_TABS_H_
