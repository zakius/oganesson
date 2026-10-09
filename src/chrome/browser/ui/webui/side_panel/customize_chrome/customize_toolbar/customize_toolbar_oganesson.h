// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SIDE_PANEL_CUSTOMIZE_CHROME_CUSTOMIZE_TOOLBAR_CUSTOMIZE_TOOLBAR_OGANESSON_H_
#define CHROME_BROWSER_UI_WEBUI_SIDE_PANEL_CUSTOMIZE_CHROME_CUSTOMIZE_TOOLBAR_CUSTOMIZE_TOOLBAR_OGANESSON_H_

#include <vector>

#include "chrome/browser/ui/webui/side_panel/customize_chrome/customize_toolbar/customize_toolbar.mojom.h"

class PrefService;

namespace ui {
class ColorProvider;
}

// Customize toolbar's switches for the built-in toolbar items it can hide:
// back, reload, the location bar, the extensions button, the avatar and the
// app menu. Their state is prefs::kToolbarHiddenItems, which ToolbarView
// applies (toolbar_view_items.cc).

// Adds them to `actions`, with icons in `icon_color_id` at `scale_factor`.
void AppendHideableToolbarItems(
    std::vector<side_panel::customize_chrome::mojom::ActionPtr>& actions,
    const PrefService& prefs,
    const ui::ColorProvider& provider,
    int icon_color_id,
    float scale_factor);

// Shows (`pin`) or hides the item `action_id` names, if it is one of them.
// Returns whether it was.
bool PinHideableToolbarItem(
    side_panel::customize_chrome::mojom::ActionId action_id,
    bool pin,
    PrefService& prefs);

#endif  // CHROME_BROWSER_UI_WEBUI_SIDE_PANEL_CUSTOMIZE_CHROME_CUSTOMIZE_TOOLBAR_CUSTOMIZE_TOOLBAR_OGANESSON_H_
