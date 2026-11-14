// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/oganesson_settings.h"

#include <memory>

#include "build/build_config.h"
#include "chrome/browser/containers/platform/containers_desktop.h"
#include "chrome/browser/ui/webui/settings/autoplay_settings.h"
#include "chrome/browser/ui/webui/settings/browser_traffic_handler.h"
#include "chrome/browser/ui/webui/settings/history_saving_settings.h"
#include "chrome/browser/ui/webui/settings/mouse_gestures_settings.h"
#include "chrome/browser/ui/webui/settings/omnibox_suggestions_settings.h"
#include "chrome/browser/ui/webui/settings/shortcuts_page_handler.h"
#include "chrome/grit/oganesson_strings.h"
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
  // Privacy and security > Containers.
  containers::AddSettingsStrings(html_source);
  // Privacy and security > Browser traffic, in place of Helium's services.
  web_ui->AddMessageHandler(std::make_unique<BrowserTrafficHandler>(profile));
  BrowserTrafficHandler::AddStrings(html_source);
  AddHistorySavingStrings(html_source);
  // Renames the shortcuts page.
  AddMouseGestureStrings(html_source);
  AddOmniboxSuggestionsStrings(html_source);
  web_ui->AddMessageHandler(std::make_unique<ShortcutsPageHandler>(
      profile, web_ui->GetWebContents()));
  // Appearance > App icon.
  static constexpr webui::LocalizedString kAppIconStrings[] = {
      {"appIcon", IDS_OGANESSON_APP_ICON},
      {"appIconOrange", IDS_OGANESSON_APP_ICON_ORANGE},
      {"appIconTeal", IDS_OGANESSON_APP_ICON_TEAL},
      {"appIconCrimson", IDS_OGANESSON_APP_ICON_CRIMSON},
      {"appIconBlack", IDS_OGANESSON_APP_ICON_BLACK},
      {"appIconWhite", IDS_OGANESSON_APP_ICON_WHITE},
      {"appIconClearWhite", IDS_OGANESSON_APP_ICON_CLEAR_WHITE},
      {"appIconClearBlack", IDS_OGANESSON_APP_ICON_CLEAR_BLACK},
  };
  html_source->AddLocalizedStrings(kAppIconStrings);
  static constexpr webui::LocalizedString kTabStrings[] = {
      {"showTabAudioIndicator", IDS_OGANESSON_SHOW_TAB_AUDIO_INDICATOR},
      {"showTabCloseButtons", IDS_OGANESSON_SHOW_TAB_CLOSE_BUTTONS},
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
  // Search engine > Google Lens, Languages > Translation.
  static constexpr webui::LocalizedString kGoogleStrings[] = {
      {"googleLens", IDS_OGANESSON_GOOGLE_LENS},
      {"googleLensDescription", IDS_OGANESSON_GOOGLE_LENS_DESCRIPTION},
      {"oganessonTranslatePages", IDS_OGANESSON_TRANSLATE_PAGES},
      {"oganessonTranslatePagesDescription",
       IDS_OGANESSON_TRANSLATE_PAGES_DESCRIPTION},
      {"oganessonTranslateOnDevice", IDS_OGANESSON_TRANSLATE_ON_DEVICE},
      {"oganessonTranslateOnDeviceDescription",
       IDS_OGANESSON_TRANSLATE_ON_DEVICE_DESCRIPTION},
      {"oganessonTranslateGoogle", IDS_OGANESSON_TRANSLATE_GOOGLE},
      {"oganessonTranslateGoogleDescription",
       IDS_OGANESSON_TRANSLATE_GOOGLE_DESCRIPTION},
  };
  html_source->AddLocalizedStrings(kGoogleStrings);
  // Setup, chrome://settings/setup.
  static constexpr webui::LocalizedString kSetupStrings[] = {
      {"setupAskEachTime", IDS_SETUP_ASK_EACH_TIME},
      {"setupBack", IDS_SETUP_BACK},
      {"setupBangsOff", IDS_SETUP_BANGS_OFF},
      {"setupBangsOn", IDS_SETUP_BANGS_ON},
      {"setupCrashReports", IDS_SETUP_CRASH_REPORTS},
      {"setupCrashReportsDescription", IDS_SETUP_CRASH_REPORTS_DESCRIPTION},
      {"setupDefaultLead", IDS_SETUP_DEFAULT_LEAD},
      {"setupDefaultLinux", IDS_SETUP_DEFAULT_LINUX},
      {"setupDefaultTitle", IDS_SETUP_DEFAULT_TITLE},
      {"setupDefaultWindows", IDS_SETUP_DEFAULT_WINDOWS},
      {"setupDoneLead", IDS_SETUP_DONE_LEAD},
      {"setupDoneTitle", IDS_SETUP_DONE_TITLE},
      {"setupGetStarted", IDS_SETUP_GET_STARTED},
      {"setupGoogleLead", IDS_SETUP_GOOGLE_LEAD},
      {"setupImportBookmarks", IDS_SETUP_IMPORT_BOOKMARKS},
      {"setupImportExtensions", IDS_SETUP_IMPORT_EXTENSIONS},
      {"setupImportExtensionsNote", IDS_SETUP_IMPORT_EXTENSIONS_NOTE},
      {"setupImportFound", IDS_SETUP_IMPORT_FOUND},
      {"setupImportHistory", IDS_SETUP_IMPORT_HISTORY},
      {"setupImportNone", IDS_SETUP_IMPORT_NONE},
      {"setupImportPasswords", IDS_SETUP_IMPORT_PASSWORDS},
      {"setupImportPasswordsNote", IDS_SETUP_IMPORT_PASSWORDS_NOTE},
      {"setupImportTitle", IDS_SETUP_IMPORT_TITLE},
      {"setupImportWhat", IDS_SETUP_IMPORT_WHAT},
      {"setupMakeDefault", IDS_SETUP_MAKE_DEFAULT},
      {"setupNewChoiceLead", IDS_SETUP_NEW_CHOICE_LEAD},
      {"setupNewChoiceNote", IDS_SETUP_NEW_CHOICE_NOTE},
      {"setupNewChoiceTitle", IDS_SETUP_NEW_CHOICE_TITLE},
      {"setupNext", IDS_SETUP_NEXT},
      {"setupNoise", IDS_SETUP_NOISE},
      {"setupNoiseDescription", IDS_SETUP_NOISE_DESCRIPTION},
      {"setupNotNow", IDS_SETUP_NOT_NOW},
      {"setupNotSaved", IDS_SETUP_NOT_SAVED},
      {"setupNotSet", IDS_SETUP_NOT_SET},
      {"setupNothing", IDS_SETUP_NOTHING},
      {"setupOff", IDS_SETUP_OFF},
      {"setupOn", IDS_SETUP_ON},
      {"setupPasswordsDontSave", IDS_SETUP_PASSWORDS_DONT_SAVE},
      {"setupPasswordsDontSaveDescription",
       IDS_SETUP_PASSWORDS_DONT_SAVE_DESCRIPTION},
      {"setupPasswordsLead", IDS_SETUP_PASSWORDS_LEAD},
      {"setupPasswordsSave", IDS_SETUP_PASSWORDS_SAVE},
      {"setupPasswordsSaveDescription", IDS_SETUP_PASSWORDS_SAVE_DESCRIPTION},
      {"setupRunAgain", IDS_SETUP_RUN_AGAIN},
      {"setupSavedInBrowser", IDS_SETUP_SAVED_IN_BROWSER},
      {"setupSearchLead", IDS_SETUP_SEARCH_LEAD},
      {"setupSearchTitle", IDS_SETUP_SEARCH_TITLE},
      {"setupSigningIn", IDS_SETUP_SIGNING_IN},
      {"setupSkip", IDS_SETUP_SKIP},
      {"setupStartBrowsing", IDS_SETUP_START_BROWSING},
      {"setupStepDefaultBrowser", IDS_SETUP_STEP_DEFAULT_BROWSER},
      {"setupStepDone", IDS_SETUP_STEP_DONE},
      {"setupStepGoogle", IDS_SETUP_STEP_GOOGLE},
      {"setupStepImport", IDS_SETUP_STEP_IMPORT},
      {"setupStepPasswords", IDS_SETUP_STEP_PASSWORDS},
      {"setupStepPrivacy", IDS_SETUP_STEP_PRIVACY},
      {"setupStepSearch", IDS_SETUP_STEP_SEARCH},
      {"setupStepSync", IDS_SETUP_STEP_SYNC},
      {"setupStepTabs", IDS_SETUP_STEP_TABS},
      {"setupStepWelcome", IDS_SETUP_STEP_WELCOME},
      {"setupSyncLaterDescription", IDS_SETUP_SYNC_LATER_DESCRIPTION},
      {"setupSyncLead", IDS_SETUP_SYNC_LEAD},
      {"setupSyncNow", IDS_SETUP_SYNC_NOW},
      {"setupSyncNowDescription", IDS_SETUP_SYNC_NOW_DESCRIPTION},
      {"setupSyncTitle", IDS_SETUP_SYNC_TITLE},
      {"setupTabsChromium", IDS_SETUP_TABS_CHROMIUM},
      {"setupTabsFirefox", IDS_SETUP_TABS_FIREFOX},
      {"setupTabsLead", IDS_SETUP_TABS_LEAD},
      {"setupTabsNote", IDS_SETUP_TABS_NOTE},
      {"setupTabsTitle", IDS_SETUP_TABS_TITLE},
      {"setupTrafficLead", IDS_SETUP_TRAFFIC_LEAD},
      {"setupTrafficServer", IDS_SETUP_TRAFFIC_SERVER},
      {"setupTrafficTitle", IDS_SETUP_TRAFFIC_TITLE},
      {"setupWelcomeLead", IDS_SETUP_WELCOME_LEAD},
      {"setupWelcomeNote", IDS_SETUP_WELCOME_NOTE},
      {"setupWelcomeTitle", IDS_SETUP_WELCOME_TITLE},
      {"setupYes", IDS_SETUP_YES},
  };
  html_source->AddLocalizedStrings(kSetupStrings);
#if BUILDFLAG(IS_LINUX)
  web_ui->AddMessageHandler(std::make_unique<FirefoxSyncHandler>(profile));
  FirefoxSyncHandler::AddStrings(html_source);
  // The people page holds Firefox Sync, not a Google account.
  html_source->AddLocalizedString("peoplePageTitle",
                                  IDS_FIREFOX_SYNC_SECTION_TITLE);
#endif
}

}  // namespace settings
