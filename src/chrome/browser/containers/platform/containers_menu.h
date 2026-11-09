// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINERS_MENU_H_
#define CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINERS_MENU_H_

#include <memory>
#include <string>
#include <vector>

#include "base/functional/callback.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "ui/menus/simple_menu_model.h"

class BrowserWindowInterface;
class GURL;
class Profile;
class TabStripModel;

namespace bookmarks {
class BookmarkNode;
}

namespace content {
class WebContents;
}

namespace tabs {
class TabInterface;
}

namespace containers {

// A submenu of containers: "No container" (unless that is where the tab is),
// the user's containers, "New temporary container" and "Manage containers…".
// The Append* functions add it to a menu as an item with `command_id`, which
// the menu enables as it does that command, and keep it in `slot`, which must
// live as long as the menu. They add nothing for a profile without containers,
// such as an incognito one.
class ContainersMenu : public ui::SimpleMenuModel::Delegate {
 public:
  // Opens what the menu is for in container `id`, or outside containers when
  // `id` is empty.
  using OpenCallback = base::RepeatingCallback<void(const std::string& id)>;

  // "Open link in container ▸" for a link of a page in `source`.
  static void AppendForLink(ui::SimpleMenuModel* menu,
                            int command_id,
                            content::WebContents* source,
                            const GURL& url,
                            std::unique_ptr<ContainersMenu>& slot);
  // "Reopen in container ▸" for the tabs at `indices` of `model`.
  static void AppendForTabs(ui::SimpleMenuModel* menu,
                            int command_id,
                            TabStripModel* model,
                            const std::vector<int>& indices,
                            std::unique_ptr<ContainersMenu>& slot);
  // "New tab in container ▸" for the New Tab button of `browser`.
  static void AppendForNewTab(ui::SimpleMenuModel* menu,
                              int command_id,
                              BrowserWindowInterface* browser,
                              std::unique_ptr<ContainersMenu>& slot);
  // "Open in container ▸" for the bookmarks `selection`: its bookmarks and
  // those of its folders, as "Open all" opens them.
  static void AppendForBookmarks(
      ui::SimpleMenuModel* menu,
      int command_id,
      BrowserWindowInterface* browser,
      const std::vector<raw_ptr<const bookmarks::BookmarkNode,
                               VectorExperimental>>& selection,
      std::unique_ptr<ContainersMenu>& slot);

  // The menu of the address bar's container icon of `tab`: the containers to
  // reopen it in. Null when the tab can't move.
  static std::unique_ptr<ContainersMenu> ForTab(tabs::TabInterface* tab);

  ContainersMenu(const ContainersMenu&) = delete;
  ContainersMenu& operator=(const ContainersMenu&) = delete;
  ~ContainersMenu() override;

  ui::SimpleMenuModel* model() { return &model_; }

  // ui::SimpleMenuModel::Delegate:
  void ExecuteCommand(int command_id, int event_flags) override;

 private:
  ContainersMenu(Profile* profile, OpenCallback open);

  // The menu of the containers, leaving out container `current`, or null
  // when `profile` has no containers.
  static std::unique_ptr<ContainersMenu> Create(Profile* profile,
                                                const std::string& current,
                                                OpenCallback open);
  // Reopens `tabs` in the container chosen.
  static OpenCallback ReopenCallback(
      std::vector<base::WeakPtr<tabs::TabInterface>> tabs);
  // Adds the menu of Create() to `menu` as a submenu with `label`.
  static void Append(ui::SimpleMenuModel* menu,
                     int command_id,
                     int label,
                     Profile* profile,
                     const std::string& current,
                     OpenCallback open,
                     std::unique_ptr<ContainersMenu>& slot);

  const raw_ptr<Profile> profile_;
  const OpenCallback open_;
  // By item, from the first container's command id on.
  std::vector<std::string> ids_;
  ui::SimpleMenuModel model_{this};
};

}  // namespace containers

#endif  // CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINERS_MENU_H_
