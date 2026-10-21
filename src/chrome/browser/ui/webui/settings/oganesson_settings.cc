// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/oganesson_settings.h"

#include <memory>

#include "build/build_config.h"
#include "chrome/browser/ui/webui/settings/autoplay_settings.h"
#include "chrome/browser/ui/webui/settings/browser_traffic_handler.h"
#include "chrome/browser/ui/webui/settings/history_saving_settings.h"
#include "chrome/browser/ui/webui/settings/mouse_gestures_settings.h"
#include "chrome/browser/ui/webui/settings/omnibox_suggestions_settings.h"
#include "chrome/browser/ui/webui/settings/shortcuts_page_handler.h"
#include "chrome/grit/generated_resources.h"
#include "content/public/browser/web_ui.h"
#include "content/public/browser/web_ui_data_source.h"
#include "ui/base/webui/web_ui_util.h"

#if BUILDFLAG(IS_LINUX)
#include "chrome/browser/ui/webui/settings/firefox_sync_handler.h"
#endif

namespace settings {

void AddOganessonSettings(content::WebUI* web_ui,
                          content::WebUIDataSource* html_source,
                          Profile* profile) {
  AddAutoplayStrings(html_source);
  // Privacy and security > Browser traffic, in place of Helium's services.
  web_ui->AddMessageHandler(std::make_unique<BrowserTrafficHandler>(profile));
  BrowserTrafficHandler::AddStrings(html_source);
  AddHistorySavingStrings(html_source);
  // Renames the shortcuts page.
  AddMouseGestureStrings(html_source);
  AddOmniboxSuggestionsStrings(html_source);
  web_ui->AddMessageHandler(std::make_unique<ShortcutsPageHandler>(
      profile, web_ui->GetWebContents()));
  static constexpr webui::LocalizedString kTabStrings[] = {
      {"showTabAudioIndicator", IDS_OGANESSON_SHOW_TAB_AUDIO_INDICATOR},
      // Settings > Behavior > Tab behavior.
      {"tabBehavior", IDS_OGANESSON_TAB_BEHAVIOR},
      {"tabBehaviorCustom", IDS_OGANESSON_TAB_BEHAVIOR_CUSTOM},
      {"tabLinkPosition", IDS_OGANESSON_TAB_LINK_POSITION},
      {"tabLinkPositionAsIn", IDS_OGANESSON_TAB_LINK_POSITION_AS_IN},
      {"tabLinkPositionAtEnd", IDS_OGANESSON_TAB_LINK_POSITION_AT_END},
      {"tabSelectRelatedOnClose", IDS_OGANESSON_TAB_SELECT_RELATED_ON_CLOSE},
      {"tabSelectOwnerOnClose", IDS_OGANESSON_TAB_SELECT_OWNER_ON_CLOSE},
      {"tabSelectMruOnClose", IDS_OGANESSON_TAB_SELECT_MRU_ON_CLOSE},
  };
  html_source->AddLocalizedStrings(kTabStrings);
  static constexpr webui::LocalizedString kImportStrings[] = {
      {"importChooseFolder", IDS_OGANESSON_IMPORT_CHOOSE_FOLDER},
      {"importProfileFolderDescription",
       IDS_OGANESSON_IMPORT_PROFILE_FOLDER_DESCRIPTION},
      {"importNoProfileFound", IDS_OGANESSON_IMPORT_NO_PROFILE_FOUND},
  };
  html_source->AddLocalizedStrings(kImportStrings);
#if BUILDFLAG(IS_LINUX)
  web_ui->AddMessageHandler(std::make_unique<FirefoxSyncHandler>(profile));
  FirefoxSyncHandler::AddStrings(html_source);
  // The people page holds Firefox Sync, not a Google account.
  html_source->AddLocalizedString("peoplePageTitle",
                                  IDS_FIREFOX_SYNC_SECTION_TITLE);
#endif
}

}  // namespace settings
