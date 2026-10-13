// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/oganesson_settings.h"

#include <memory>

#include "build/build_config.h"
#include "chrome/browser/ui/webui/settings/autoplay_settings.h"
#include "chrome/browser/ui/webui/settings/history_saving_settings.h"
#include "chrome/browser/ui/webui/settings/mouse_gestures_settings.h"
#include "chrome/browser/ui/webui/settings/omnibox_suggestions_settings.h"
#include "chrome/grit/generated_resources.h"
#include "content/public/browser/web_ui.h"
#include "content/public/browser/web_ui_data_source.h"

#if BUILDFLAG(IS_LINUX)
#include "chrome/browser/ui/webui/settings/firefox_sync_handler.h"
#endif

namespace settings {

void AddOganessonSettings(content::WebUI* web_ui,
                          content::WebUIDataSource* html_source,
                          Profile* profile) {
  AddAutoplayStrings(html_source);
  AddHistorySavingStrings(html_source);
  // Renames the shortcuts page.
  AddMouseGestureStrings(html_source);
  AddOmniboxSuggestionsStrings(html_source);
  html_source->AddLocalizedString("showTabAudioIndicator",
                                  IDS_OGANESSON_SHOW_TAB_AUDIO_INDICATOR);
#if BUILDFLAG(IS_LINUX)
  web_ui->AddMessageHandler(std::make_unique<FirefoxSyncHandler>(profile));
  FirefoxSyncHandler::AddStrings(html_source);
  // The people page holds Firefox Sync, not a Google account.
  html_source->AddLocalizedString("peoplePageTitle",
                                  IDS_FIREFOX_SYNC_SECTION_TITLE);
#endif
}

}  // namespace settings
