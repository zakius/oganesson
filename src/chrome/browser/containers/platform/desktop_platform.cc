// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// dubna's containers_platform.h for the desktop browser.

#include <utility>
#include <vector>

#include "base/callback_list.h"
#include "base/functional/bind.h"
#include "base/functional/callback_helpers.h"
#include "base/scoped_observation.h"
#include "base/strings/utf_string_conversions.h"
#include "chrome/browser/containers/container.h"
#include "chrome/browser/containers/containers_platform.h"
#include "chrome/browser/containers/containers_tabs.h"
#include "chrome/browser/containers/platform/containers_desktop.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/sessions/session_restore.h"
#include "chrome/browser/sessions/session_service.h"
#include "chrome/browser/sessions/session_service_factory.h"
#include "chrome/browser/ui/browser_window/public/browser_collection_observer.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/browser_window/public/global_browser_collection.h"
#include "chrome/browser/ui/browser_window/public/profile_browser_collection.h"
#include "chrome/browser/ui/dialogs/browser_dialogs.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "chrome/browser/ui/tab_contents/tab_contents_iterator.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/common/webui_url_constants.h"
#include "chrome/grit/generated_resources.h"
#include "components/sessions/core/session_types.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/web_contents.h"
#include "content/public/common/url_constants.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/models/dialog_model.h"
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

namespace {

// The question, on `browser`: a dialog whose default button keeps the
// container. Closing it, or Escape, answers nothing: it comes back at the
// next start.
void Ask(BrowserWindowInterface* browser,
         const Container& container,
         base::OnceCallback<void(bool)> callback) {
  int open_tabs = 0;
  for (tabs::TabInterface* tab : TabsOf(browser->GetProfile())) {
    if (ContainerIdOf(tab->GetContents()) == container.id) {
      ++open_tabs;
    }
  }
  auto [delete_it, keep_it] = base::SplitOnceCallback(std::move(callback));
  chrome::ShowBrowserModal(
      browser,
      ui::DialogModel::Builder()
          .SetInternalName("SyncDeletedContainerDialog")
          .SetTitle(l10n_util::GetStringFUTF16(
              IDS_CONTAINERS_SYNC_DELETED_TITLE,
              base::UTF8ToUTF16(container.name)))
          .AddParagraph(ui::DialogModelLabel(l10n_util::GetPluralStringFUTF16(
              IDS_CONTAINERS_SYNC_DELETED_BODY, open_tabs)))
          .AddOkButton(base::BindOnce(std::move(delete_it), true),
                       ui::DialogModel::Button::Params().SetLabel(
                           l10n_util::GetStringUTF16(
                               IDS_CONTAINERS_SYNC_DELETED_DELETE)))
          .AddCancelButton(base::BindOnce(std::move(keep_it), false),
                           ui::DialogModel::Button::Params().SetLabel(
                               l10n_util::GetStringUTF16(
                                   IDS_CONTAINERS_SYNC_DELETED_KEEP)))
          .OverrideDefaultButton(ui::mojom::DialogButton::kCancel)
          .Build());
}

// Asks once `profile` has a window and its session is restored, so the
// question counts the restored tabs: at a start, the question comes before
// both. Deletes itself then.
class AskWhenRestored : public BrowserCollectionObserver {
 public:
  AskWhenRestored(Profile* profile,
                  const Container& container,
                  base::OnceCallback<void(bool)> callback)
      : profile_(profile->GetWeakPtr()),
        container_(container),
        callback_(std::move(callback)),
        restored_(SessionRestore::RegisterOnSessionRestoredCallback(
            base::BindRepeating(&AskWhenRestored::OnSessionRestored,
                                base::Unretained(this)))) {
    observation_.Observe(GlobalBrowserCollection::GetInstance());
  }

  // `restored`: the profile's session restore has just finished, though it
  // still counts as restoring.
  void AskIfReady(bool restored = false) {
    if (!profile_) {
      delete this;
      return;
    }
    BrowserWindowInterface* browser =
        ProfileBrowserCollection::GetForProfile(profile_.get())
            ->FindTabbedBrowser();
    if (!browser ||
        (!restored && SessionRestore::IsRestoring(profile_.get()))) {
      return;
    }
    // Gone before the dialog shows: it activates the window again.
    Container container = container_;
    base::OnceCallback<void(bool)> callback = std::move(callback_);
    delete this;
    Ask(browser, container, std::move(callback));
  }

  // BrowserCollectionObserver:
  void OnBrowserActivated(BrowserWindowInterface* browser) override {
    AskIfReady();
  }

 private:
  void OnSessionRestored(Profile* profile, int tabs) {
    AskIfReady(profile == profile_.get());
  }

  base::WeakPtr<Profile> profile_;
  Container container_;
  base::OnceCallback<void(bool)> callback_;
  base::CallbackListSubscription restored_;
  base::ScopedObservation<GlobalBrowserCollection, BrowserCollectionObserver>
      observation_{this};
};

}  // namespace

void AskToDeleteSyncedContainer(Profile* profile,
                                const Container& container,
                                base::OnceCallback<void(bool)> callback) {
  (new AskWhenRestored(profile, container, std::move(callback)))->AskIfReady();
}

}  // namespace containers
