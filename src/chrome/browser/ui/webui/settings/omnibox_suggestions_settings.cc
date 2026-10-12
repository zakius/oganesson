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
      {"omniboxSearchSuggestionsFirst",
       IDS_SETTINGS_OMNIBOX_SEARCH_SUGGESTIONS_FIRST},
      {"omniboxSearchSuggestionsFirstDescription",
       IDS_SETTINGS_OMNIBOX_SEARCH_SUGGESTIONS_FIRST_DESCRIPTION},
  };
  html_source->AddLocalizedStrings(kStrings);
}

}  // namespace settings
