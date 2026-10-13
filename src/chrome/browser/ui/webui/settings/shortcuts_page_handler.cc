// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/shortcuts_page_handler.h"

#include <algorithm>
#include <string>

#include "base/functional/bind.h"
#include "base/strings/utf_string_conversions.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_shortcuts/browser_shortcut_service.h"
#include "chrome/browser/ui/browser_shortcuts/browser_shortcut_service_factory.h"
#include "chrome/browser/ui/webui/settings/mouse_gestures_settings.h"
#include "content/public/browser/web_ui.h"

namespace settings {

ShortcutsPageHandler::ShortcutsPageHandler(Profile* profile,
                                           content::WebContents* web_contents)
    : profile_(profile), capture_suspender_(web_contents) {}

ShortcutsPageHandler::~ShortcutsPageHandler() = default;

void ShortcutsPageHandler::RegisterMessages() {
  web_ui()->RegisterMessageCallback(
      "setShortcutHandlingSuspended",
      base::BindRepeating(
          &ShortcutsPageHandler::HandleSetShortcutHandlingSuspended,
          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "getShortcutCommandName",
      base::BindRepeating(&ShortcutsPageHandler::HandleGetCommandName,
                          base::Unretained(this)));
  web_ui()->RegisterMessageCallback(
      "getGestureExtensionCommands",
      base::BindRepeating(&ShortcutsPageHandler::HandleGetExtensionCommands,
                          base::Unretained(this)));
}

void ShortcutsPageHandler::OnJavascriptDisallowed() {
  capture_suspender_.SetSuspended(false);
}

void ShortcutsPageHandler::HandleSetShortcutHandlingSuspended(
    const base::ListValue& args) {
  // So that OnJavascriptDisallowed() resumes them when the page goes away.
  AllowJavascript();
  capture_suspender_.SetSuspended(args.size() == 1 && args[0].is_bool() &&
                                  args[0].GetBool());
}

void ShortcutsPageHandler::HandleGetCommandName(const base::ListValue& args) {
  AllowJavascript();
  std::string name;
  auto* service =
      browser_shortcuts::BrowserShortcutServiceFactory::GetForProfile(profile_);
  if (service && args.size() == 2 && args[1].is_int()) {
    const auto& commands = service->GetCommands();
    auto it = std::ranges::find(commands, args[1].GetInt(),
                                &browser_shortcuts::CommandInfo::command_id);
    if (it != commands.end()) {
      name = base::UTF16ToUTF8(it->name);
    }
  }
  ResolveJavascriptCallback(args[0], name);
}

void ShortcutsPageHandler::HandleGetExtensionCommands(
    const base::ListValue& args) {
  AllowJavascript();
  ResolveJavascriptCallback(args[0], GetGestureExtensionCommands(profile_));
}

}  // namespace settings
