// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SETTINGS_AUTOPLAY_SETTINGS_H_
#define CHROME_BROWSER_UI_WEBUI_SETTINGS_AUTOPLAY_SETTINGS_H_

namespace content {
class WebUIDataSource;
}

namespace settings {

// Strings of the Site settings Autoplay page and of the Autoplay menu of a
// site's permissions.
void AddAutoplayStrings(content::WebUIDataSource* html_source);

}  // namespace settings

#endif  // CHROME_BROWSER_UI_WEBUI_SETTINGS_AUTOPLAY_SETTINGS_H_
