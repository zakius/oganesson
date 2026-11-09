// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINER_PAGE_ACTION_H_
#define CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINER_PAGE_ACTION_H_

#include <memory>

#include "base/memory/raw_ref.h"
#include "base/scoped_observation.h"
#include "chrome/browser/containers/containers_service.h"
#include "ui/base/unowned_user_data/scoped_unowned_user_data.h"

class BrowserWindowInterface;

namespace actions {
class ActionItem;
}

namespace page_actions {
class PageActionController;
}

namespace tabs {
class TabInterface;
}

namespace views {
class MenuRunner;
}

namespace containers {

class ContainersMenu;

// The address bar icon of a tab in a container: the container's icon in its
// color, with its name in the tooltip (Helium's address bar shows page
// actions as icons only). A click opens the menu to reopen the tab in another
// container. One per tab, owned by its TabFeatures.
class ContainerPageAction : public ContainersService::Observer {
 public:
  DECLARE_USER_DATA(ContainerPageAction);

  ContainerPageAction(tabs::TabInterface& tab,
                      page_actions::PageActionController& controller);
  ContainerPageAction(const ContainerPageAction&) = delete;
  ContainerPageAction& operator=(const ContainerPageAction&) = delete;
  ~ContainerPageAction() override;

  // The browser's action for the icon, which the page actions of its tabs
  // use.
  static std::unique_ptr<actions::ActionItem> CreateActionItem(
      BrowserWindowInterface* browser);

  // ContainersService::Observer:
  void OnContainersChanged() override;

 private:
  // Shows the icon of the tab's container, or hides it.
  void Update();
  void ShowMenu();

  const raw_ref<tabs::TabInterface> tab_;
  const raw_ref<page_actions::PageActionController> controller_;
  base::ScopedObservation<ContainersService, ContainersService::Observer>
      observation_{this};
  // The open menu. The runner is destroyed first.
  std::unique_ptr<ContainersMenu> menu_;
  std::unique_ptr<views::MenuRunner> menu_runner_;
  ui::ScopedUnownedUserData<ContainerPageAction> scoped_unowned_user_data_;
};

}  // namespace containers

#endif  // CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINER_PAGE_ACTION_H_
