// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/containers/platform/containers_desktop.h"

#include <memory>
#include <utility>

#include "base/containers/fixed_flat_map.h"
#include "base/strings/strcat.h"
#include "base/strings/string_util.h"
#include "chrome/app/vector_icons/vector_icons.h"
#include "chrome/browser/containers/container.h"
#include "chrome/browser/containers/containers_service.h"
#include "chrome/browser/containers/containers_service_factory.h"
#include "chrome/browser/containers/containers_tabs.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_tabstrip.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/chrome_pages.h"
#include "chrome/browser/ui/navigator/browser_navigator.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/grit/generated_resources.h"
#include "components/tabs/public/tab_interface.h"
#include "components/vector_icons/vector_icons.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/web_contents.h"
#include "content/public/browser/web_ui_data_source.h"
#include "ui/base/webui/web_ui_util.h"
#include "ui/gfx/color_utils.h"
#include "ui/gfx/image/image_skia.h"
#include "ui/gfx/paint_vector_icon.h"
#include "ui/gfx/canvas.h"
#include "ui/gfx/geometry/rect.h"
#include "url/gurl.h"

namespace containers {

namespace {

// Firefox's icon names, drawn with Chromium's nearest icons.
const gfx::VectorIcon& VectorIconOf(std::string_view icon) {
  static constexpr auto kIcons =
      base::MakeFixedFlatMap<std::string_view, const gfx::VectorIcon*>({
          {"fingerprint", &vector_icons::kFingerprintIcon},
          {"briefcase", &vector_icons::kWorkIcon},
          {"dollar", &vector_icons::kPaymentsIcon},
          {"cart", &vector_icons::kShoppingBagIcon},
          {"gift", &kStarIcon},
          {"vacation", &vector_icons::kFlightIcon},
          {"pet", &vector_icons::kPetsIcon},
          {"chill", &vector_icons::kVideogameAssetIcon},
          {"fence", &vector_icons::kLockIcon},
      });
  auto it = kIcons.find(icon);
  return it == kIcons.end() ? kCircleFilledIcon : *it->second;
}

struct Choice {
  const char* name;
  // Its name for screen readers.
  int message;
};

// The colors the user picks from: Firefox's, but its toolbar gray.
constexpr Choice kColors[] = {
    {"blue", IDS_OGANESSON_CONTAINERS_COLOR_BLUE},
    {"turquoise", IDS_OGANESSON_CONTAINERS_COLOR_TURQUOISE},
    {"green", IDS_OGANESSON_CONTAINERS_COLOR_GREEN},
    {"yellow", IDS_OGANESSON_CONTAINERS_COLOR_YELLOW},
    {"orange", IDS_OGANESSON_CONTAINERS_COLOR_ORANGE},
    {"red", IDS_OGANESSON_CONTAINERS_COLOR_RED},
    {"pink", IDS_OGANESSON_CONTAINERS_COLOR_PINK},
    {"purple", IDS_OGANESSON_CONTAINERS_COLOR_PURPLE},
};
constexpr Choice kIconNames[] = {
    {"fingerprint", IDS_OGANESSON_CONTAINERS_ICON_FINGERPRINT},
    {"briefcase", IDS_OGANESSON_CONTAINERS_ICON_BRIEFCASE},
    {"dollar", IDS_OGANESSON_CONTAINERS_ICON_DOLLAR},
    {"cart", IDS_OGANESSON_CONTAINERS_ICON_CART},
    {"circle", IDS_OGANESSON_CONTAINERS_ICON_CIRCLE},
    {"gift", IDS_OGANESSON_CONTAINERS_ICON_GIFT},
    {"vacation", IDS_OGANESSON_CONTAINERS_ICON_VACATION},
    {"pet", IDS_OGANESSON_CONTAINERS_ICON_PET},
    {"chill", IDS_OGANESSON_CONTAINERS_ICON_CHILL},
    {"fence", IDS_OGANESSON_CONTAINERS_ICON_FENCE},
};

}  // namespace

void AddSettingsStrings(content::WebUIDataSource* source) {
  static constexpr webui::LocalizedString kStrings[] = {
      {"containersTitle", IDS_OGANESSON_CONTAINERS_TITLE},
      {"containersDescription", IDS_OGANESSON_CONTAINERS_DESCRIPTION},
      {"containersAdd", IDS_OGANESSON_CONTAINERS_ADD},
      {"containersEdit", IDS_OGANESSON_CONTAINERS_EDIT},
      {"containersName", IDS_OGANESSON_CONTAINERS_NAME},
      {"containersColor", IDS_OGANESSON_CONTAINERS_COLOR},
      {"containersIcon", IDS_OGANESSON_CONTAINERS_ICON},
      {"containersDeleteTitle", IDS_OGANESSON_CONTAINERS_DELETE_TITLE},
      {"containersDeleteBody", IDS_OGANESSON_CONTAINERS_DELETE_BODY},
      {"containersNoneYet", IDS_OGANESSON_CONTAINERS_NONE_YET},
      {"containersNewTabs", IDS_OGANESSON_CONTAINERS_NEW_TABS},
      {"trafficControlTitle", IDS_OGANESSON_TRAFFIC_CONTROL_TITLE},
      {"trafficControlDescription", IDS_OGANESSON_TRAFFIC_CONTROL_DESCRIPTION},
      {"trafficControlAdd", IDS_OGANESSON_TRAFFIC_CONTROL_ADD},
      {"trafficControlEdit", IDS_OGANESSON_TRAFFIC_CONTROL_EDIT},
      {"trafficControlSites", IDS_OGANESSON_TRAFFIC_CONTROL_SITES},
      {"trafficControlSitesInvalid",
       IDS_OGANESSON_TRAFFIC_CONTROL_SITES_INVALID},
      {"trafficControlOpenIn", IDS_OGANESSON_TRAFFIC_CONTROL_OPEN_IN},
      {"trafficControlNone", IDS_OGANESSON_TRAFFIC_CONTROL_NONE},
      {"trafficControlTemporary", IDS_OGANESSON_TRAFFIC_CONTROL_TEMPORARY},
      {"trafficControlNoneYet", IDS_OGANESSON_TRAFFIC_CONTROL_NONE_YET},
  };
  source->AddLocalizedStrings(kStrings);
  std::vector<std::string> colors;
  for (const Choice& color : kColors) {
    colors.push_back(color.name);
    source->AddLocalizedString(base::StrCat({"containerColorName_", color.name}),
                               color.message);
  }
  source->AddString("containerColors", base::JoinString(colors, ","));
  for (const char* color : {"blue", "turquoise", "green", "yellow", "orange",
                            "red", "pink", "purple", "toolbar"}) {
    source->AddString(
        base::StrCat({"containerColor_", color}),
        color_utils::SkColorToRgbaString(Container{.color = color}.color_value()));
  }
  std::vector<std::string> icons;
  for (const Choice& icon : kIconNames) {
    icons.push_back(icon.name);
    source->AddLocalizedString(base::StrCat({"containerIconName_", icon.name}),
                               icon.message);
    // White on transparent, for the page to use as a mask in any color.
    gfx::ImageSkia image =
        gfx::CreateVectorIcon(VectorIconOf(icon.name), 32, SK_ColorWHITE);
    source->AddString(base::StrCat({"containerIcon_", icon.name}),
                      webui::GetBitmapDataUrl(*image.bitmap()));
  }
  source->AddString("containerIcons", base::JoinString(icons, ","));
}

ui::ImageModel IconOf(const Container& container, int size) {
  return ui::ImageModel::FromVectorIcon(VectorIconOf(container.icon),
                                        container.color_value(), size);
}

ui::ImageModel IconImageOf(const Container& container, int size) {
  return ui::ImageModel::FromImageSkia(gfx::CreateVectorIcon(
      VectorIconOf(container.icon), size, container.color_value()));
}

void NavigateInContainer(NavigateParams* params, const std::string& id) {
  if (id.empty()) {
    Navigate(params);
    return;
  }
  Profile* profile = params->browser->GetProfile();
  content::WebContents::CreateParams create_params(
      profile, SiteInstanceIn(profile, id, params->url));
  create_params.initially_hidden =
      params->disposition == WindowOpenDisposition::NEW_BACKGROUND_TAB;
  params->contents_to_insert = content::WebContents::Create(create_params);
  content::WebContents* contents = params->contents_to_insert.get();
  Navigate(params);
  // Navigate() stopped early and left it to go with `params`.
  if (params->contents_to_insert) {
    return;
  }
  // Loads once in its tab strip, where its tab helpers watch it.
  content::NavigationController::LoadURLParams load(params->url);
  load.transition_type = params->transition;
  load.initiator_origin = params->initiator_origin;
  load.referrer = params->referrer;
  contents->GetController().LoadURLWithParams(load);
  params->navigated_or_inserted_contents = contents;
}

content::WebContents* OpenInContainer(BrowserWindowInterface* browser,
                                      const GURL& url,
                                      const std::string& id,
                                      WindowOpenDisposition disposition,
                                      content::WebContents* source) {
  NavigateParams params(browser, url, ui::PAGE_TRANSITION_LINK);
  params.disposition = disposition;
  params.source_contents = source;
  if (source) {
    params.tabstrip_add_types |= AddTabTypes::ADD_INHERIT_OPENER;
  }
  NavigateInContainer(&params, id);
  return params.navigated_or_inserted_contents;
}

std::string NewTabContainer(BrowserWindowInterface* browser) {
  ContainersService* service =
      ContainersServiceFactory::GetForProfile(browser->GetProfile());
  return service ? service->NewTabContainer() : std::string();
}

void NewTabInContainer(BrowserWindowInterface* browser, const std::string& id) {
  OpenInContainer(browser, chrome::GetNewTabURL(browser), id,
                  WindowOpenDisposition::NEW_FOREGROUND_TAB);
}

void ReopenTabsInContainer(const std::vector<tabs::TabInterface*>& tabs,
                           const std::string& id) {
  for (tabs::TabInterface* tab : tabs) {
    BrowserWindowInterface* browser = tab->GetBrowserWindowInterface();
    TabStripModel* model = browser->GetTabStripModel();
    content::WebContents* old_contents = tab->GetContents();
    // Already there: reopening would only lose its history.
    if (ContainerIdOf(old_contents) == id) {
      continue;
    }
    const bool pinned = tab->IsPinned();
    content::WebContents* contents = OpenInContainer(
        browser, old_contents->GetLastCommittedURL(), id,
        tab->IsActivated() ? WindowOpenDisposition::NEW_FOREGROUND_TAB
                           : WindowOpenDisposition::NEW_BACKGROUND_TAB,
        old_contents);
    int index = contents ? model->GetIndexOfWebContents(contents)
                         : TabStripModel::kNoTab;
    if (index == TabStripModel::kNoTab) {
      continue;
    }
    // In the old tab's place.
    if (pinned) {
      index = model->SetTabPinned(index, true);
    }
    int old_index = model->GetIndexOfWebContents(old_contents);
    model->MoveWebContentsAt(index, old_index < index ? old_index + 1 : old_index,
                             false);
    tab->Close();
  }
}

void ShowContainersSettings(Profile* profile) {
  chrome::ShowSettingsSubPageForProfile(profile, "containers");
}

void PaintTabLine(const tabs::TabInterface* const_tab,
                  const gfx::Rect& bounds,
                  gfx::Canvas* canvas) {
  // GetBrowserWindowInterface() isn't const.
  auto* tab = const_cast<tabs::TabInterface*>(const_tab);
  if (!tab || !tab->GetContents()) {
    return;
  }
  std::string id = ContainerIdOf(tab->GetContents());
  ContainersService* service =
      id.empty() || !tab->GetBrowserWindowInterface() ? nullptr
                 : ContainersServiceFactory::GetForProfile(
                       tab->GetBrowserWindowInterface()->GetProfile());
  std::optional<Container> container = service ? service->Get(id) : std::nullopt;
  if (!container) {
    return;
  }
  constexpr int kHeight = 2;
  canvas->FillRect(gfx::Rect(bounds.x(), bounds.bottom() - kHeight,
                             bounds.width(), kHeight),
                   container->color_value());
}

}  // namespace containers
