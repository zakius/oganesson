// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/firefox_sync/tabs_adapter.h"

#include "base/strings/utf_string_conversions.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/browser_window/public/profile_browser_collection.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "content/public/browser/web_contents.h"
#include "url/gurl.h"

namespace firefox_sync {

TabsAdapter::TabsAdapter(Profile* profile, base::RepeatingClosure local_changed)
    : profile_(profile),
      local_changed_(std::move(local_changed)),
      tracker_(this, this) {
  tracker_.Init();
}

TabsAdapter::~TabsAdapter() = default;

bool TabsAdapter::ShouldTrackBrowser(BrowserWindowInterface* browser) {
  return browser->GetProfile() == profile_ &&
         browser->GetType() == BrowserWindowInterface::TYPE_NORMAL;
}

void TabsAdapter::GetLocal(base::OnceCallback<void(base::Value)> done) {
  base::ListValue tabs;
  ProfileBrowserCollection::GetForProfile(profile_)->ForEach(
      [&](BrowserWindowInterface* browser) {
        if (!ShouldTrackBrowser(browser)) {
          return true;
        }
        auto* model = browser->GetTabStripModel();
        for (int i = 0; i < model->count(); ++i) {
          auto* contents = model->GetWebContentsAt(i);
          const GURL& url = contents->GetVisibleURL();
          if (!url.SchemeIsHTTPOrHTTPS()) {
            continue;
          }
          base::DictValue tab;
          tab.Set("url", url.spec());
          tab.Set("title", base::UTF16ToUTF8(contents->GetTitle()));
          tab.Set("lastUsed",
                  static_cast<double>(contents->GetLastActiveTime()
                                          .InMillisecondsSinceUnixEpoch()));
          tab.Set("pinned", model->IsTabPinned(i));
          tabs.Append(std::move(tab));
        }
        return true;
      });
  std::move(done).Run(base::Value(std::move(tabs)));
}

void TabsAdapter::Apply(const base::ListValue& ops) {}

void TabsAdapter::OnTabStripModelChanged(
    TabStripModel* model,
    const TabStripModelChange& change,
    const TabStripSelectionChange& selection) {
  local_changed_.Run();
}

void TabsAdapter::OnTabChangedAt(tabs::TabInterface* tab,
                                 TabChangeType change_type) {
  local_changed_.Run();
}

void TabsAdapter::OnTabPinnedStateChanged(tabs::TabInterface* tab, int index) {
  local_changed_.Run();
}

}  // namespace firefox_sync
