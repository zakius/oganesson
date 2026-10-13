// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_PREFS_EDITOR_PREFS_EDITOR_UI_H_
#define CHROME_BROWSER_UI_WEBUI_PREFS_EDITOR_PREFS_EDITOR_UI_H_

#include "content/public/browser/web_ui_controller.h"
#include "content/public/browser/webui_config.h"
#include "content/public/common/url_constants.h"

class PrefsEditorUI;

// Also listed in chrome::ChromeURLHosts(), by value.
inline constexpr char kChromeUIPrefsEditorHost[] = "config";

// chrome://config (about:config): every pref, editable, like Firefox's
// about:config.
class PrefsEditorUIConfig : public content::DefaultWebUIConfig<PrefsEditorUI> {
 public:
  PrefsEditorUIConfig()
      : DefaultWebUIConfig(content::kChromeUIScheme,
                           kChromeUIPrefsEditorHost) {}
};

class PrefsEditorUI : public content::WebUIController {
 public:
  explicit PrefsEditorUI(content::WebUI* web_ui);
  PrefsEditorUI(const PrefsEditorUI&) = delete;
  PrefsEditorUI& operator=(const PrefsEditorUI&) = delete;
  ~PrefsEditorUI() override;
};

#endif  // CHROME_BROWSER_UI_WEBUI_PREFS_EDITOR_PREFS_EDITOR_UI_H_
