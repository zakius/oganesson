// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_COMMON_EXTENSIONS_API_SIDE_PANEL_FIREFOX_SIDEBAR_ACTION_H_
#define CHROME_COMMON_EXTENSIONS_API_SIDE_PANEL_FIREFOX_SIDEBAR_ACTION_H_

#include <memory>
#include <string>

#include "chrome/common/extensions/api/side_panel/side_panel_info.h"

namespace extensions {

class Extension;

// Firefox's sidebar_action manifest key (dubna's webextensions/README.md):
// its default_panel is the add-on's side panel, as Chromium's side_panel key
// gives one, without the sidePanel permission Firefox add-ons don't ask for.
inline constexpr char kFirefoxSidebarAction[] = "sidebar_action";

// Whether `extension` gets its side panel from sidebar_action: it has that
// key and not Chromium's own side_panel, which wins when both are there.
bool IsFirefoxSidebar(const Extension& extension);

// The side panel of such an add-on. Without a valid default_panel, null with
// `error` set, as Chromium's side_panel without a valid default_path.
std::unique_ptr<SidePanelInfo> ParseFirefoxSidebar(const Extension& extension,
                                                   std::u16string* error);

}  // namespace extensions

#endif  // CHROME_COMMON_EXTENSIONS_API_SIDE_PANEL_FIREFOX_SIDEBAR_ACTION_H_
