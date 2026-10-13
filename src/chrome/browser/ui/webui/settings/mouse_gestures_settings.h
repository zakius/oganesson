// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SETTINGS_MOUSE_GESTURES_SETTINGS_H_
#define CHROME_BROWSER_UI_WEBUI_SETTINGS_MOUSE_GESTURES_SETTINGS_H_

#include "base/values.h"

class Profile;

namespace content {
class WebUIDataSource;
}

namespace settings {

// The commands of the profile's enabled extensions that a mouse gesture can
// run: their named commands and their action's command, each as
// {extensionId, commandName, name}.
base::ListValue GetGestureExtensionCommands(Profile* profile);

// The strings and flags of the gestures on the "Shortcuts and gestures"
// page; its title too, which they rename.
void AddMouseGestureStrings(content::WebUIDataSource* html_source);

}  // namespace settings

#endif  // CHROME_BROWSER_UI_WEBUI_SETTINGS_MOUSE_GESTURES_SETTINGS_H_
