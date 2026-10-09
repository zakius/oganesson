// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_PREFS_EDITOR_PREFS_EDITOR_UI_H_
#define CHROME_BROWSER_UI_WEBUI_PREFS_EDITOR_PREFS_EDITOR_UI_H_

#include "chrome/common/webui_url_constants.h"
#include "content/public/browser/web_ui_controller.h"
#include "content/public/browser/webui_config.h"

class PrefsEditorUI;

// chrome://config (about:config): every pref, editable, like Firefox's
// about:config.
class PrefsEditorUIConfig : public content::DefaultWebUIConfig<PrefsEditorUI> {
 public:
  PrefsEditorUIConfig()
      : DefaultWebUIConfig(content::kChromeUIScheme,
                           chrome::kChromeUIPrefsEditorHost) {}
};

class PrefsEditorUI : public content::WebUIController {
 public:
  explicit PrefsEditorUI(content::WebUI* web_ui);
  PrefsEditorUI(const PrefsEditorUI&) = delete;
  PrefsEditorUI& operator=(const PrefsEditorUI&) = delete;
  ~PrefsEditorUI() override;
};

#endif  // CHROME_BROWSER_UI_WEBUI_PREFS_EDITOR_PREFS_EDITOR_UI_H_
