// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/web_applications/web_install_badge.h"

#include <optional>
#include <string>

#include "chrome/browser/ui/actions/chrome_action_id.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/page_action/page_action_controller.h"
#include "chrome/browser/ui/page_action/page_action_triggers.h"
#include "chrome/browser/web_applications/web_install_request.h"
#include "chrome/grit/oganesson_strings.h"
#include "components/tabs/public/tab_interface.h"
#include "components/vector_icons/vector_icons.h"
#include "content/public/browser/web_contents.h"
#include "ui/actions/actions.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/models/image_model.h"
#include "ui/color/color_id.h"
#include "ui/gfx/vector_icon_types.h"

namespace web_app {

namespace {

// A dot in the top right corner of the 20 dip install icon, in the icon's
// color, with a ring cleared around it.
constexpr gfx::PathElement kBadgePath[] = {
    gfx::CANVAS_DIMENSIONS, 20,
    gfx::PATH_MODE_CLEAR, gfx::CIRCLE, 17.75f, 2.75f, 2.75f,
    gfx::NEW_PATH, gfx::CIRCLE, 17.75f, 2.75f, 2,
};
constexpr gfx::VectorIconRep kBadgeRep[] = {{kBadgePath}};
constexpr gfx::VectorIcon kBadge(kBadgeRep, 1u, "oganesson_web_install_badge");

}  // namespace

bool ShowWebInstallBadge(page_actions::PageActionController& controller,
                         content::WebContents& web_contents) {
  // A tab whose page never asked has nothing to put back.
  if (!WebInstallRequest::FromWebContents(&web_contents)) {
    return false;
  }
  if (!WebInstallRequest::Has(&web_contents)) {
    controller.ClearOverrideImage(kActionInstallPwa);
    controller.OverrideForegroundColor(kActionInstallPwa, std::nullopt);
    return false;
  }
  // The address bar draws a vector icon in its foreground color: here the
  // accent color, so the icon stands out beside the others.
  controller.OverrideImage(
      kActionInstallPwa,
      ui::ImageModel::FromVectorIcon(vector_icons::kInstallDesktopIcon,
                                     ui::kColorIcon, 0, &kBadge));
  controller.OverrideForegroundColor(kActionInstallPwa, ui::kColorAccent);
  const std::u16string tooltip =
      l10n_util::GetStringUTF16(IDS_OGANESSON_WEB_INSTALL_REQUEST);
  controller.OverrideTooltip(kActionInstallPwa, tooltip);
  controller.OverrideAccessibleName(kActionInstallPwa, tooltip);
  controller.HideSuggestionChip(kActionInstallPwa);
  controller.Show(kActionInstallPwa);
  return true;
}

bool RunWebInstallRequest(BrowserWindowInterface* browser,
                          const actions::ActionInvocationContext& context) {
  if (context.GetProperty(page_actions::kPageActionTriggerKey) ==
      page_actions::kInvalidPageActionTrigger) {
    return false;
  }
  tabs::TabInterface* tab = browser->GetActiveTabInterface();
  return tab && WebInstallRequest::Run(tab->GetContents());
}

}  // namespace web_app
