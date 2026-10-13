// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/autoplay_settings.h"

#include "chrome/grit/generated_resources.h"
#include "content/public/browser/web_ui_data_source.h"
#include "ui/base/webui/web_ui_util.h"

namespace settings {

void AddAutoplayStrings(content::WebUIDataSource* html_source) {
  static constexpr webui::LocalizedString kStrings[] = {
      {"siteSettingsAutoplay", IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY},
      {"siteSettingsAutoplayMidSentence",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_MID_SENTENCE},
      {"siteSettingsAutoplayDescription",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_DESCRIPTION},
      {"siteSettingsAutoplayAllow", IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_ALLOW},
      {"siteSettingsAutoplayBlockAudio",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_BLOCK_AUDIO},
      {"siteSettingsAutoplayBlockAudioSubLabel",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_BLOCK_AUDIO_SUB_LABEL},
      {"siteSettingsAutoplayBlock", IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_BLOCK},
      {"siteSettingsAutoplayBlockSubLabel",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_BLOCK_SUB_LABEL},
      {"siteSettingsAutoplayAllowedExceptions",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_ALLOWED_EXCEPTIONS},
      {"siteSettingsAutoplayBlockedExceptions",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_BLOCKED_EXCEPTIONS},
      {"siteSettingsAutoplayAllowDefault",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_ALLOW_DEFAULT},
      {"siteSettingsAutoplayBlockAudioDefault",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_BLOCK_AUDIO_DEFAULT},
      {"siteSettingsAutoplayBlockDefault",
       IDS_SETTINGS_SITE_SETTINGS_AUTOPLAY_BLOCK_DEFAULT},
  };
  html_source->AddLocalizedStrings(kStrings);
}

}  // namespace settings
