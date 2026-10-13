// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/omnibox_suggestions_settings.h"

#include "chrome/grit/generated_resources.h"
#include "content/public/browser/web_ui_data_source.h"
#include "ui/base/webui/web_ui_util.h"

namespace settings {

void AddOmniboxSuggestionsStrings(content::WebUIDataSource* html_source) {
  static constexpr webui::LocalizedString kStrings[] = {
      {"omniboxSuggestions", IDS_SETTINGS_OMNIBOX_SUGGESTIONS},
      {"omniboxSuggestionsDescription",
       IDS_SETTINGS_OMNIBOX_SUGGESTIONS_DESCRIPTION},
      {"omniboxSuggestHistory", IDS_SETTINGS_OMNIBOX_SUGGEST_HISTORY},
      {"omniboxSuggestBookmarks", IDS_SETTINGS_OMNIBOX_SUGGEST_BOOKMARKS},
      {"omniboxSuggestOpenTabs", IDS_SETTINGS_OMNIBOX_SUGGEST_OPEN_TABS},
      {"omniboxSuggestOpenTabsDescription",
       IDS_SETTINGS_OMNIBOX_SUGGEST_OPEN_TABS_DESCRIPTION},
      {"omniboxSuggestPastSearches", IDS_SETTINGS_OMNIBOX_SUGGEST_PAST_SEARCHES},
      {"omniboxSuggestPastSearchesDescription",
       IDS_SETTINGS_OMNIBOX_SUGGEST_PAST_SEARCHES_DESCRIPTION},
      {"omniboxHistoryNotSaved", IDS_SETTINGS_OMNIBOX_HISTORY_NOT_SAVED},
      {"omniboxSuggestionOrder", IDS_SETTINGS_OMNIBOX_SUGGESTION_ORDER},
      {"omniboxSuggestionOrderDescription",
       IDS_SETTINGS_OMNIBOX_SUGGESTION_ORDER_DESCRIPTION},
      {"omniboxSearches", IDS_SETTINGS_OMNIBOX_SEARCHES},
      {"omniboxGroupOff", IDS_SETTINGS_OMNIBOX_GROUP_OFF},
      {"omniboxMoveUp", IDS_SETTINGS_OMNIBOX_MOVE_UP},
      {"omniboxMoveDown", IDS_SETTINGS_OMNIBOX_MOVE_DOWN},
  };
  html_source->AddLocalizedStrings(kStrings);
}

}  // namespace settings
