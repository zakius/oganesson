// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/common/extensions/api/side_panel/firefox_sidebar_action.h"

#include "chrome/common/extensions/api/side_panel.h"
#include "extensions/common/extension.h"
#include "extensions/common/manifest.h"
#include "extensions/common/manifest_constants.h"

namespace extensions {

bool IsFirefoxSidebar(const Extension& extension) {
  const base::DictValue& values = extension.manifest()->available_values();
  return values.FindDict(kFirefoxSidebarAction) &&
         !values.contains(api::side_panel::ManifestKeys::kSidePanel);
}

std::unique_ptr<SidePanelInfo> ParseFirefoxSidebar(const Extension& extension,
                                                   std::u16string* error) {
  const base::DictValue* sidebar =
      extension.manifest()->available_values().FindDict(kFirefoxSidebarAction);
  const std::string* panel =
      sidebar ? sidebar->FindString("default_panel") : nullptr;
  if (!panel || !extension.GetResourceURL(*panel).is_valid()) {
    *error = manifest_errors::kSidePanelManifestDefaultPathInvalid;
    return nullptr;
  }
  auto info = std::make_unique<SidePanelInfo>();
  info->default_path = *panel;
  return info;
}

}  // namespace extensions
