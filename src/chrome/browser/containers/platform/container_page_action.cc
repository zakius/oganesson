// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/containers/platform/container_page_action.h"

#include <optional>
#include <string>
#include <vector>

#include "base/functional/bind.h"
#include "base/strings/utf_string_conversions.h"
#include "chrome/browser/containers/container.h"
#include "chrome/browser/containers/containers_service_factory.h"
#include "chrome/browser/containers/containers_tabs.h"
#include "chrome/browser/containers/platform/containers_desktop.h"
#include "chrome/browser/containers/platform/containers_menu.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/actions/chrome_action_id.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/page_action/page_action_controller.h"
#include "chrome/browser/ui/views/frame/browser_view.h"
#include "chrome/browser/ui/views/frame/toolbar_button_provider.h"
#include "chrome/browser/ui/views/tabs/common/tab_view.h"
#include "chrome/browser/ui/views/tabs/tab.h"
#include "chrome/grit/oganesson_strings.h"
#include "components/tabs/public/tab_interface.h"
#include "ui/actions/actions.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/mojom/menu_source_type.mojom.h"
#include "ui/views/bubble/bubble_anchor.h"
#include "ui/views/controls/menu/menu_runner.h"
#include "ui/views/view.h"
#include "ui/views/view_utils.h"
#include "ui/views/widget/widget.h"

namespace containers {

DEFINE_USER_DATA(ContainerPageAction);

namespace {

// Repaints `tab` in its window's tab strip, horizontal or vertical: Chromium
// repaints a tab only when its title, icon or state change.
void RepaintTab(tabs::TabInterface& tab) {
  BrowserWindowInterface* browser = tab.GetBrowserWindowInterface();
  BrowserView* browser_view =
      browser ? BrowserView::GetBrowserViewForBrowser(browser) : nullptr;
  if (!browser_view) {
    return;
  }
  std::vector<views::View*> views = {browser_view};
  while (!views.empty()) {
    views::View* view = views.back();
    views.pop_back();
    ::Tab* horizontal = views::AsViewClass<::Tab>(view);
    ::TabView* vertical = views::AsViewClass<::TabView>(view);
    if ((horizontal && horizontal->tab_handle().Get() == &tab) ||
        (vertical && vertical->GetTabInterface() == &tab)) {
      view->SchedulePaint();
    }
    for (views::View* child : view->children()) {
      views.push_back(child);
    }
  }
}

}  // namespace

ContainerPageAction::ContainerPageAction(
    tabs::TabInterface& tab,
    page_actions::PageActionController& controller)
    : tab_(tab),
      controller_(controller),
      scoped_unowned_user_data_(tab.GetUnownedUserDataHost(), *this) {
  // A tab stays in the container its contents were made in, a discarded tab's
  // new contents too: only the container itself changes.
  if (ContainersService* service =
          ContainersServiceFactory::GetForProfile(tab.GetProfile())) {
    observation_.Observe(service);
  }
  Update();
}

ContainerPageAction::~ContainerPageAction() = default;

// static
std::unique_ptr<actions::ActionItem> ContainerPageAction::CreateActionItem(
    BrowserWindowInterface* browser) {
  return actions::ActionItem::Builder(
             base::BindRepeating(
                 [](BrowserWindowInterface* browser, actions::ActionItem* item,
                    actions::ActionInvocationContext context) {
                   tabs::TabInterface* tab = browser->GetActiveTabInterface();
                   ContainerPageAction* action =
                       tab ? Get(tab->GetUnownedUserDataHost()) : nullptr;
                   if (action) {
                     action->ShowMenu();
                   }
                 },
                 browser))
      .SetActionId(kActionShowContainer)
      .Build();
}

void ContainerPageAction::OnContainersChanged() {
  const SkColor before = line_color_;
  Update();
  if (line_color_ != before) {
    RepaintTab(*tab_);
  }
}

void ContainerPageAction::Update() {
  ContainersService* service = observation_.GetSource();
  std::string id = ContainerIdOf(tab_->GetContents());
  std::optional<Container> container =
      service && !id.empty() ? service->Get(id) : std::nullopt;
  line_color_ = container ? container->color_value() : SK_ColorTRANSPARENT;
  if (!container) {
    controller_->Hide(kActionShowContainer);
    return;
  }
  const std::u16string name = l10n_util::GetStringFUTF16(
      IDS_OGANESSON_CONTAINERS_PAGE_ACTION, base::UTF8ToUTF16(container->name));
  // An image, not a vector icon, which the address bar would recolor.
  controller_->OverrideImage(kActionShowContainer, IconImageOf(*container));
  controller_->OverrideTooltip(kActionShowContainer, name);
  controller_->OverrideAccessibleName(kActionShowContainer, name);
  controller_->Show(kActionShowContainer);
}

void ContainerPageAction::ShowMenu() {
  BrowserView* browser_view =
      tab_->GetBrowserWindowInterface()
          ? BrowserView::GetBrowserViewForBrowser(
                tab_->GetBrowserWindowInterface())
          : nullptr;
  views::View* anchor =
      browser_view ? browser_view->toolbar_button_provider()
                         ->GetPageActionBubbleAnchor(kActionShowContainer)
                         .GetIfView()
                   : nullptr;
  if (!anchor || !anchor->GetWidget()) {
    return;
  }
  menu_runner_.reset();
  menu_ = ContainersMenu::ForTab(&tab_.get());
  if (!menu_) {
    return;
  }
  menu_runner_ = std::make_unique<views::MenuRunner>(
      menu_->model(), views::MenuRunner::HAS_MNEMONICS);
  menu_runner_->RunMenuAt(anchor->GetWidget(), nullptr,
                          anchor->GetAnchorBoundsInScreen(),
                          views::MenuAnchorPosition::kTopRight,
                          ui::mojom::MenuSourceType::kMouse);
}

}  // namespace containers
