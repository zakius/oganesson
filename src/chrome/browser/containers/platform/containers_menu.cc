// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/containers/platform/containers_menu.h"

#include <utility>

#include "base/functional/bind.h"
#include "base/memory/ptr_util.h"
#include "base/no_destructor.h"
#include "base/task/sequenced_task_runner.h"
#include "base/strings/utf_string_conversions.h"
#include "chrome/app/chrome_command_ids.h"
#include "chrome/browser/containers/container.h"
#include "chrome/browser/containers/containers_service.h"
#include "chrome/browser/containers/containers_service_factory.h"
#include "chrome/browser/containers/containers_tabs.h"
#include "chrome/browser/containers/platform/containers_desktop.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "components/prefs/pref_service.h"
#include "chrome/grit/oganesson_strings.h"
#include "components/bookmarks/browser/bookmark_node.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/web_contents.h"
#include "ui/base/accelerators/menu_label_accelerator_util.h"
#include "ui/base/mojom/menu_source_type.mojom.h"
#include "ui/display/screen.h"
#include "ui/views/controls/menu/menu_runner.h"
#include "ui/views/view.h"
#include "url/gurl.h"

namespace containers {

// static
void ContainersMenu::AppendForLink(ui::SimpleMenuModel* menu,
                                   int command_id,
                                   content::WebContents* source,
                                   const GURL& url,
                                   std::unique_ptr<ContainersMenu>& slot) {
  tabs::TabInterface* tab =
      source ? tabs::TabInterface::MaybeGetFromContents(source) : nullptr;
  BrowserWindowInterface* browser =
      tab ? tab->GetBrowserWindowInterface() : nullptr;
  if (!browser || browser->GetType() != BrowserWindowInterface::TYPE_NORMAL ||
      !url.SchemeIsHTTPOrHTTPS()) {
    return;
  }
  Append(menu, command_id, IDS_OGANESSON_CONTAINERS_OPEN_LINK,
         browser->GetProfile(), ContainerIdOf(source),
         base::BindRepeating(
             [](base::WeakPtr<content::WebContents> source, const GURL& url,
                const std::string& id) {
               tabs::TabInterface* tab =
                   source ? tabs::TabInterface::MaybeGetFromContents(
                                source.get())
                          : nullptr;
               if (tab && tab->GetBrowserWindowInterface()) {
                 OpenInContainer(tab->GetBrowserWindowInterface(), url, id,
                                 WindowOpenDisposition::kNewBackgroundTab,
                                 source.get());
               }
             },
             source->GetWeakPtr(), url),
         slot);
}

// static
void ContainersMenu::AppendForTabs(ui::SimpleMenuModel* menu,
                                   int command_id,
                                   TabStripModel* model,
                                   const std::vector<int>& indices,
                                   std::unique_ptr<ContainersMenu>& slot) {
  std::vector<base::WeakPtr<tabs::TabInterface>> tabs;
  std::string current;
  for (int index : indices) {
    tabs::TabInterface* tab = model->GetTabAtIndex(index);
    if (!tab->GetContents()->GetLastCommittedURL().SchemeIsHTTPOrHTTPS()) {
      continue;
    }
    // Leaves out a container only when every tab is in it.
    std::string id = ContainerIdOf(tab->GetContents());
    current = tabs.empty() || id == current ? id : "-";
    tabs.push_back(tab->GetWeakPtr());
  }
  if (tabs.empty()) {
    return;
  }
  Append(menu, command_id, IDS_OGANESSON_CONTAINERS_REOPEN, model->profile(),
         current, ReopenCallback(std::move(tabs)), slot);
}

// static
std::unique_ptr<ContainersMenu> ContainersMenu::ForTab(tabs::TabInterface* tab) {
  BrowserWindowInterface* browser = tab->GetBrowserWindowInterface();
  content::WebContents* contents = tab->GetContents();
  if (!browser || !contents ||
      !contents->GetLastCommittedURL().SchemeIsHTTPOrHTTPS()) {
    return nullptr;
  }
  return Create(browser->GetProfile(), ContainerIdOf(contents),
                ReopenCallback({tab->GetWeakPtr()}));
}

// static
bool ContainersMenu::AskForNewTab(BrowserWindowInterface* browser,
                                  views::View* source) {
  Profile* profile = browser->GetProfile();
  if (profile->GetPrefs()->GetString(kNewTabContainer) != kAskForNewTab) {
    return false;
  }
  // "-" is no container's id: the menu has "No container" and every container.
  std::unique_ptr<ContainersMenu> menu = Create(
      profile, "-",
      base::BindRepeating(
          [](base::WeakPtr<BrowserWindowInterface> browser,
             const std::string& id) {
            if (browser) {
              NewTabInContainer(browser.get(), id);
            }
          },
          browser->GetWeakPtr()));
  if (!menu) {
    return false;
  }
  // The open menu, kept until it closes. The runner is destroyed first.
  struct Open {
    std::unique_ptr<ContainersMenu> menu;
    std::unique_ptr<views::MenuRunner> runner;
    // Counts the menus shown.
    int shown = 0;
  };
  static base::NoDestructor<Open> open;
  open->runner.reset();
  open->menu = std::move(menu);
  open->runner = std::make_unique<views::MenuRunner>(
      open->menu->model(), views::MenuRunner::HAS_MNEMONICS,
      base::BindRepeating(
          [](int closed) {
            // After the menu has run its command, unless another one opened.
            base::SequencedTaskRunner::GetCurrentDefault()->PostTask(
                FROM_HERE, base::BindOnce(
                               [](int closed) {
                                 if (open->shown == closed) {
                                   open->runner.reset();
                                   open->menu.reset();
                                 }
                               },
                               closed));
          },
          ++open->shown));
  open->runner->RunMenuAt(
      source->GetWidget(), nullptr,
      gfx::Rect(display::Screen::Get()->GetCursorScreenPoint(), gfx::Size()),
      views::MenuAnchorPosition::kTopLeft, ui::mojom::MenuSourceType::kMouse);
  return true;
}

// static
ContainersMenu::OpenCallback ContainersMenu::ReopenCallback(
    std::vector<base::WeakPtr<tabs::TabInterface>> tabs) {
  return base::BindRepeating(
      [](const std::vector<base::WeakPtr<tabs::TabInterface>>& tabs,
         const std::string& id) {
        std::vector<tabs::TabInterface*> alive;
        for (const auto& tab : tabs) {
          if (tab) {
            alive.push_back(tab.get());
          }
        }
        ReopenTabsInContainer(alive, id);
      },
      std::move(tabs));
}

// static
void ContainersMenu::AppendForNewTab(ui::SimpleMenuModel* menu,
                                     int command_id,
                                     BrowserWindowInterface* browser,
                                     std::unique_ptr<ContainersMenu>& slot) {
  // Incognito and guest windows have no containers.
  if (!ContainersServiceFactory::GetForProfile(browser->GetProfile())) {
    return;
  }
  menu->AddSeparator(ui::NORMAL_SEPARATOR);
  Append(menu, command_id, IDS_OGANESSON_CONTAINERS_NEW_TAB,
         browser->GetProfile(), std::string(),
         base::BindRepeating(
             [](base::WeakPtr<BrowserWindowInterface> browser,
                const std::string& id) {
               if (browser) {
                 NewTabInContainer(browser.get(), id);
               }
             },
             browser->GetWeakPtr()),
         slot);
}

// static
void ContainersMenu::AppendForBookmarks(
    ui::SimpleMenuModel* menu,
    int command_id,
    BrowserWindowInterface* browser,
    const std::vector<raw_ptr<const bookmarks::BookmarkNode,
                             VectorExperimental>>& selection,
    std::unique_ptr<ContainersMenu>& slot) {
  std::vector<GURL> urls;
  for (const bookmarks::BookmarkNode* node : selection) {
    if (node->is_url()) {
      urls.push_back(node->url());
      continue;
    }
    for (const auto& child : node->children()) {
      if (child->is_url()) {
        urls.push_back(child->url());
      }
    }
  }
  std::erase_if(urls, [](const GURL& url) { return !url.SchemeIsHTTPOrHTTPS(); });
  if (!browser || browser->GetType() != BrowserWindowInterface::TYPE_NORMAL ||
      urls.empty()) {
    return;
  }
  Append(menu, command_id, IDS_OGANESSON_CONTAINERS_OPEN_BOOKMARKS,
         browser->GetProfile(), std::string(),
         base::BindRepeating(
             [](base::WeakPtr<BrowserWindowInterface> browser,
                const std::vector<GURL>& urls, const std::string& id) {
               if (!browser) {
                 return;
               }
               for (const GURL& url : urls) {
                 OpenInContainer(browser.get(), url, id,
                                 &url == &urls.front()
                                     ? WindowOpenDisposition::kNewForegroundTab
                                     : WindowOpenDisposition::kNewBackgroundTab);
               }
             },
             browser->GetWeakPtr(), std::move(urls)),
         slot);
}

// static
void ContainersMenu::Append(ui::SimpleMenuModel* menu,
                            int command_id,
                            int label,
                            Profile* profile,
                            const std::string& current,
                            OpenCallback open,
                            std::unique_ptr<ContainersMenu>& slot) {
  std::unique_ptr<ContainersMenu> submenu =
      Create(profile, current, std::move(open));
  if (!submenu) {
    return;
  }
  slot = std::move(submenu);
  menu->AddSubMenuWithStringId(command_id, label, &slot->model_);
}

// static
std::unique_ptr<ContainersMenu> ContainersMenu::Create(
    Profile* profile,
    const std::string& current,
    OpenCallback open) {
  ContainersService* service = ContainersServiceFactory::GetForProfile(profile);
  if (!service) {
    return nullptr;
  }
  auto submenu =
      base::WrapUnique(new ContainersMenu(profile, std::move(open)));
  ui::SimpleMenuModel& model = submenu->model_;
  if (!current.empty()) {
    model.AddItemWithStringId(IDC_OGANESSON_CONTAINERS_NONE,
                              IDS_OGANESSON_CONTAINERS_NONE);
    model.AddSeparator(ui::NORMAL_SEPARATOR);
  }
  for (const Container& container : service->GetContainers()) {
    const int next = IDC_OGANESSON_CONTAINERS_FIRST +
                     static_cast<int>(submenu->ids_.size());
    if (next > IDC_OGANESSON_CONTAINERS_LAST) {
      break;
    }
    if (container.id == current) {
      continue;
    }
    model.AddItemWithIcon(
        next,
        ui::EscapeMenuLabelAmpersands(base::UTF8ToUTF16(container.name)),
        IconOf(container));
    submenu->ids_.push_back(container.id);
  }
  model.AddItemWithStringId(IDC_OGANESSON_CONTAINERS_TEMPORARY,
                            IDS_OGANESSON_CONTAINERS_NEW_TEMPORARY);
  model.AddSeparator(ui::NORMAL_SEPARATOR);
  model.AddItemWithStringId(IDC_OGANESSON_CONTAINERS_MANAGE,
                            IDS_OGANESSON_CONTAINERS_MANAGE);
  return submenu;
}

ContainersMenu::ContainersMenu(Profile* profile, OpenCallback open)
    : profile_(profile), open_(std::move(open)) {}

ContainersMenu::~ContainersMenu() = default;

void ContainersMenu::ExecuteCommand(int command_id, int event_flags) {
  ContainersService* service = ContainersServiceFactory::GetForProfile(profile_);
  if (!service) {
    return;
  }
  switch (command_id) {
    case IDC_OGANESSON_CONTAINERS_NONE:
      open_.Run(std::string());
      return;
    case IDC_OGANESSON_CONTAINERS_TEMPORARY:
      open_.Run(service->CreateTemporary().id);
      return;
    case IDC_OGANESSON_CONTAINERS_MANAGE:
      ShowContainersSettings(profile_);
      return;
  }
  const size_t index = command_id - IDC_OGANESSON_CONTAINERS_FIRST;
  if (index >= ids_.size()) {
    return;
  }
  // The container may have been deleted while the menu was open. Get() still
  // finds it while its storage is being deleted.
  for (const Container& container : service->GetContainers()) {
    if (container.id == ids_[index]) {
      open_.Run(ids_[index]);
      return;
    }
  }
}

}  // namespace containers
