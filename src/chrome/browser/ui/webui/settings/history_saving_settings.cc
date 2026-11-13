// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/history_saving_settings.h"

#include "chrome/grit/oganesson_strings.h"
#include "content/public/browser/web_ui_data_source.h"
#include "ui/base/webui/web_ui_util.h"

namespace settings {

void AddHistorySavingStrings(content::WebUIDataSource* html_source) {
  static constexpr webui::LocalizedString kStrings[] = {
      {"historySavingDisabled", IDS_SETTINGS_HISTORY_SAVING_DISABLED},
      {"historySavingDisabledDescription",
       IDS_SETTINGS_HISTORY_SAVING_DISABLED_DESCRIPTION},
      {"keepClosedTabs", IDS_SETTINGS_KEEP_CLOSED_TABS},
      {"keepClosedTabsDescription", IDS_SETTINGS_KEEP_CLOSED_TABS_DESCRIPTION},
      {"downloadHistorySavingDisabled",
       IDS_SETTINGS_DOWNLOAD_HISTORY_SAVING_DISABLED},
      {"downloadHistorySavingDisabledDescription",
       IDS_SETTINGS_DOWNLOAD_HISTORY_SAVING_DISABLED_DESCRIPTION},
  };
  html_source->AddLocalizedStrings(kStrings);
}

}  // namespace settings
