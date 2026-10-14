// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/side_panel/customize_chrome/customize_toolbar/customize_toolbar_oganesson.h"

#include <string_view>

#include "base/containers/span.h"
#include "base/values.h"
#include "chrome/common/pref_names.h"
#include "chrome/grit/generated_resources.h"
#include "components/prefs/pref_service.h"
#include "components/prefs/scoped_user_pref_update.h"
#include "components/vector_icons/vector_icons.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/models/image_model.h"
#include "ui/gfx/image/image_skia.h"
#include "chrome/browser/ui/webui/util/image_util.h"
#include "url/gurl.h"

namespace {

using side_panel::customize_chrome::mojom::ActionId;
using side_panel::customize_chrome::mojom::CategoryId;

struct HideableItem {
  ActionId id;
  // Its prefs::kToolbarItems token.
  std::string_view token;
  int label;
  const gfx::VectorIcon& icon;
  CategoryId category;
};

base::span<const HideableItem> Items() {
  // Helium's toolbar-button-prefs lists Back, Reload, Extensions, the profile
  // button, the menu and media controls, with its helium.browser.show_*
  // prefs; the address bar is ours.
  static const HideableItem kItems[] = {
      {ActionId::kLocationBar, "location_bar",
       IDS_OGANESSON_TOOLBAR_ITEM_LOCATION_BAR, vector_icons::kSearchIcon,
       CategoryId::kNavigation},
  };
  return kItems;
}

bool IsHidden(const PrefService& prefs, std::string_view token) {
  return std::ranges::contains(prefs.GetList(prefs::kToolbarHiddenItems),
                               base::Value(token));
}

}  // namespace

void AppendHideableToolbarItems(
    std::vector<side_panel::customize_chrome::mojom::ActionPtr>& actions,
    const PrefService& prefs,
    const ui::ColorProvider& provider,
    int icon_color_id,
    float scale_factor) {
  for (const HideableItem& item : Items()) {
    actions.push_back(side_panel::customize_chrome::mojom::Action::New(
        item.id, l10n_util::GetStringUTF8(item.label),
        !IsHidden(prefs, item.token), /*has_enterprise_controlled_pinned_state=*/
        false, item.category,
        GURL(webui::EncodePNGAndMakeDataURI(
            ui::ImageModel::FromVectorIcon(item.icon, icon_color_id)
                .Rasterize(&provider),
            scale_factor))));
  }
}

bool PinHideableToolbarItem(ActionId action_id, bool pin, PrefService& prefs) {
  for (const HideableItem& item : Items()) {
    if (item.id != action_id) {
      continue;
    }
    ScopedListPrefUpdate update(&prefs, prefs::kToolbarHiddenItems);
    update->EraseValue(base::Value(item.token));
    if (!pin) {
      update->Append(item.token);
    }
    return true;
  }
  return false;
}
