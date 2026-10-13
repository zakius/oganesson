// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SETTINGS_OGANESSON_SETTINGS_H_
#define CHROME_BROWSER_UI_WEBUI_SETTINGS_OGANESSON_SETTINGS_H_

class Profile;

namespace content {
class WebUI;
class WebUIDataSource;
}  // namespace content

namespace settings {

// The strings and message handlers of oganesson's settings. Runs after
// Chromium's strings, so the ones it gives another text win.
void AddOganessonSettings(content::WebUI* web_ui,
                          content::WebUIDataSource* html_source,
                          Profile* profile);

}  // namespace settings

#endif  // CHROME_BROWSER_UI_WEBUI_SETTINGS_OGANESSON_SETTINGS_H_
