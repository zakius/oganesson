// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SETTINGS_OMNIBOX_SUGGESTIONS_SETTINGS_H_
#define CHROME_BROWSER_UI_WEBUI_SETTINGS_OMNIBOX_SUGGESTIONS_SETTINGS_H_

namespace content {
class WebUIDataSource;
}

namespace settings {

// Strings of <settings-omnibox-suggestions> on the Manage search engines page.
void AddOmniboxSuggestionsStrings(content::WebUIDataSource* html_source);

}  // namespace settings

#endif  // CHROME_BROWSER_UI_WEBUI_SETTINGS_OMNIBOX_SUGGESTIONS_SETTINGS_H_
