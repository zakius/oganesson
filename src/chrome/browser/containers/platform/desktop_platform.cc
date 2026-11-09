// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// dubna's containers_platform.h for the desktop browser.

#include <utility>
#include <vector>

#include "base/functional/bind.h"
#include "chrome/browser/containers/containers_platform.h"
#include "chrome/browser/containers/containers_tabs.h"
#include "chrome/browser/containers/platform/containers_desktop.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/sessions/session_service.h"
#include "chrome/browser/sessions/session_service_factory.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "chrome/browser/ui/tab_contents/tab_contents_iterator.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/common/webui_url_constants.h"
#include "components/sessions/core/session_types.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/web_contents.h"
#include "content/public/common/url_constants.h"
#include "url/gurl.h"

namespace containers {

namespace {

// A tab with nothing to keep: no history, and a blank or new tab page. A
// popup that a page holds as window.opener (an OAuth popup) is kept: closing
// it would cut the page off from it.
bool IsEmptyTab(content::WebContents* contents) {
  if (contents->HasOpener()) {
    return false;
  }
  content::NavigationController& controller = contents->GetController();
  if (controller.CanGoBack() || controller.GetEntryCount() > 1) {
    return false;
  }
  const GURL& url = contents->GetLastCommittedURL();
  return controller.IsInitialBlankNavigation() || url.IsAboutBlank() ||
         (url.SchemeIs(content::kChromeUIScheme) &&
          (url.host() == chrome::kChromeUINewTabHost ||
           url.host() == chrome::kChromeUINewTabPageHost));
}

// `profile`'s tabs.
std::vector<tabs::TabInterface*> TabsOf(Profile* profile) {
  std::vector<tabs::TabInterface*> found;
  tabs::ForEachTabInterface([&](tabs::TabInterface* tab) {
    BrowserWindowInterface* browser = tab->GetBrowserWindowInterface();
    if (browser && browser->GetProfile() == profile && tab->GetContents()) {
      found.push_back(tab);
    }
    return true;
  });
  return found;
}

}  // namespace

void ReopenNavigation(content::WebContents* source,
                      const GURL& url,
                      const std::string& container_id,
                      ui::PageTransition transition,
                      const std::optional<url::Origin>& initiator) {
  tabs::TabInterface* tab = tabs::TabInterface::MaybeGetFromContents(source);
  BrowserWindowInterface* browser =
      tab ? tab->GetBrowserWindowInterface() : nullptr;
  if (!browser) {
    return;
  }
  const bool empty = IsEmptyTab(source);
  NavigateParams params(browser, url, transition);
  params.initiator_origin = initiator;
  params.disposition = tab->IsActivated()
                           ? WindowOpenDisposition::NEW_FOREGROUND_TAB
                           : WindowOpenDisposition::NEW_BACKGROUND_TAB;
  params.source_contents = source;
  params.tabstrip_add_types |= AddTabTypes::ADD_INHERIT_OPENER;
  NavigateInContainer(&params, container_id);
  if (empty) {
    tab->Close();
  }
}

void GetContainersInUse(
    Profile* profile,
    base::OnceCallback<void(std::set<std::string>)> callback) {
  std::set<std::string> ids;
  for (tabs::TabInterface* tab : TabsOf(profile)) {
    std::string id = ContainerIdOf(tab->GetContents());
    if (!id.empty()) {
      ids.insert(std::move(id));
    }
  }
  SessionService* session = SessionServiceFactory::GetForProfile(profile);
  if (!session) {
    std::move(callback).Run(std::move(ids));
    return;
  }
  session->GetLastSession(base::BindOnce(
      [](std::set<std::string> ids,
         base::OnceCallback<void(std::set<std::string>)> callback,
         std::vector<std::unique_ptr<sessions::SessionWindow>> windows,
         SessionID, sessions::CommandStorageReadStatus,
         sessions::SessionReplayResult) {
        for (const auto& window : windows) {
          for (const auto& tab : window->tabs) {
            AddContainerIds(tab->navigations, ids);
          }
        }
        std::move(callback).Run(std::move(ids));
      },
      std::move(ids), std::move(callback)));
}

void CloseTabsInContainer(Profile* profile, const std::string& id) {
  for (tabs::TabInterface* tab : TabsOf(profile)) {
    if (ContainerIdOf(tab->GetContents()) != id) {
      continue;
    }
    TabStripModel* model = tab->GetBrowserWindowInterface()->GetTabStripModel();
    int index = model->GetIndexOfTab(tab);
    if (index != TabStripModel::kNoTab) {
      model->CloseWebContentsAt(index, TabCloseTypes::CLOSE_NONE);
    }
  }
}

}  // namespace containers
