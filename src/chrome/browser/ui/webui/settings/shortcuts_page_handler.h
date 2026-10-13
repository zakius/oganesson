// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SETTINGS_SHORTCUTS_PAGE_HANDLER_H_
#define CHROME_BROWSER_UI_WEBUI_SETTINGS_SHORTCUTS_PAGE_HANDLER_H_

#include "base/memory/raw_ptr.h"
#include "base/values.h"
#include "chrome/browser/ui/webui/settings/shortcut_capture_suspender.h"
#include "content/public/browser/web_ui_message_handler.h"

class Profile;

namespace content {
class WebContents;
}

namespace settings {

// What oganesson adds to the "Shortcuts and gestures" page beyond Helium's
// BrowserShortcutsHandler: suspending the window's shortcuts while a shortcut
// is recorded, and the commands mouse gestures can run. One per settings tab,
// unlike BrowserShortcutsHandler, which the page's factory replaces each time
// it's asked for one.
class ShortcutsPageHandler : public content::WebUIMessageHandler {
 public:
  ShortcutsPageHandler(Profile* profile, content::WebContents* web_contents);
  ShortcutsPageHandler(const ShortcutsPageHandler&) = delete;
  ShortcutsPageHandler& operator=(const ShortcutsPageHandler&) = delete;
  ~ShortcutsPageHandler() override;

  // content::WebUIMessageHandler:
  void RegisterMessages() override;
  // The page went away or its renderer is gone: shortcuts work again.
  void OnJavascriptDisallowed() override;

 private:
  // [suspended]
  void HandleSetShortcutHandlingSuspended(const base::ListValue& args);
  // [callbackId, commandId] -> the browser command's name, or "".
  void HandleGetCommandName(const base::ListValue& args);
  // [callbackId] -> the extension commands a gesture can run.
  void HandleGetExtensionCommands(const base::ListValue& args);

  raw_ptr<Profile> profile_;
  ShortcutCaptureSuspender capture_suspender_;
};

}  // namespace settings

#endif  // CHROME_BROWSER_UI_WEBUI_SETTINGS_SHORTCUTS_PAGE_HANDLER_H_
