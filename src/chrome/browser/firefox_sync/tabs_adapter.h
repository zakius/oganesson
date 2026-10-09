// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_FIREFOX_SYNC_TABS_ADAPTER_H_
#define CHROME_BROWSER_FIREFOX_SYNC_TABS_ADAPTER_H_

#include "base/functional/callback.h"
#include "base/memory/raw_ptr.h"
#include "chrome/browser/firefox_sync/sync_adapter.h"
#include "chrome/browser/ui/browser_tab_strip_tracker.h"
#include "chrome/browser/ui/browser_tab_strip_tracker_delegate.h"
#include "chrome/browser/ui/tabs/tab_strip_model_observer.h"

class Profile;

namespace firefox_sync {

class TabsAdapter : public SyncAdapter,
                    public BrowserTabStripTrackerDelegate,
                    public TabStripModelObserver {
 public:
  TabsAdapter(Profile* profile, base::RepeatingClosure local_changed);
  ~TabsAdapter() override;

  void GetLocal(base::OnceCallback<void(base::Value)> done) override;
  void Apply(const base::ListValue& ops) override;

 private:
  bool ShouldTrackBrowser(BrowserWindowInterface* browser) override;
  void OnTabStripModelChanged(TabStripModel* model,
                              const TabStripModelChange& change,
                              const TabStripSelectionChange& selection) override;
  void OnTabChangedAt(tabs::TabInterface* tab,
                      TabChangeType change_type) override;
  void OnTabPinnedStateChanged(tabs::TabInterface* tab, int index) override;

  const raw_ptr<Profile> profile_;
  base::RepeatingClosure local_changed_;
  BrowserTabStripTracker tracker_;
};

}  // namespace firefox_sync

#endif  // CHROME_BROWSER_FIREFOX_SYNC_TABS_ADAPTER_H_
