// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/mouse_gestures_settings.h"

#include <string>

#include "base/strings/utf_string_conversions.h"
#include "chrome/browser/extensions/commands/command_service.h"
#include "chrome/browser/profiles/profile.h"
#include "build/build_config.h"
#include "chrome/grit/generated_resources.h"
#include "chrome/grit/oganesson_strings.h"
#include "content/public/browser/web_ui_data_source.h"
#include "extensions/browser/extension_registry.h"
#include "extensions/common/api/extension_action/action_info.h"
#include "extensions/common/command.h"
#include "ui/base/l10n/l10n_util.h"

namespace settings {

base::ListValue GetGestureExtensionCommands(Profile* profile) {
  base::ListValue result;
  const auto* command_service = extensions::CommandService::Get(profile);
  const auto add = [&](const extensions::Extension& extension,
                       const ui::Command& command) {
    const std::u16string description =
        command.description().empty()
            ? l10n_util::GetStringUTF16(IDS_EXTENSION_COMMANDS_GENERIC_ACTIVATE)
            : command.description();
    result.Append(
        base::DictValue()
            .Set("extensionId", extension.id())
            .Set("commandName", command.command_name())
            .Set("name", extension.name() + ": " +
                             base::UTF16ToUTF8(description)));
  };
  for (const auto& extension :
       extensions::ExtensionRegistry::Get(profile)->enabled_extensions()) {
    ui::CommandMap commands;
    command_service->GetNamedCommands(
        extension->id(), extensions::CommandService::ALL,
        extensions::CommandService::ANY_SCOPE, &commands);
    for (const auto& [name, command] : commands) {
      add(*extension, command);
    }
    const extensions::ActionInfo* action =
        extensions::ActionInfo::GetExtensionActionInfo(extension.get());
    extensions::Command action_command;
    if (action && command_service->GetExtensionActionCommand(
                      extension->id(), action->type,
                      extensions::CommandService::ALL, &action_command,
                      nullptr)) {
      add(*extension, action_command);
    }
  }
  return result;
}

void AddMouseGestureStrings(content::WebUIDataSource* html_source) {
  // Mouse gestures are only recognized on Aura.
  constexpr bool kShow = BUILDFLAG(IS_LINUX) || BUILDFLAG(IS_WIN);
  html_source->AddBoolean("showMouseGestures", kShow);
  if (!kShow) {
    return;
  }
  static constexpr webui::LocalizedString kStrings[] = {
      {"shortcutsPageTitle", IDS_SETTINGS_SHORTCUTS_AND_GESTURES_TITLE},
      {"shortcutsAddGesture", IDS_SETTINGS_SHORTCUTS_ADD_GESTURE},
      {"shortcutsExtensionCommands", IDS_SETTINGS_SHORTCUTS_EXTENSION_COMMANDS},
      {"shortcutsAddGestureDialogTitle",
       IDS_SETTINGS_SHORTCUTS_ADD_GESTURE_DIALOG_TITLE},
      {"shortcutsGestureDescription",
       IDS_SETTINGS_SHORTCUTS_GESTURE_DESCRIPTION},
      {"shortcutsGestureLabel", IDS_SETTINGS_SHORTCUTS_GESTURE_LABEL},
      {"shortcutsGestureStroke", IDS_SETTINGS_SHORTCUTS_GESTURE_STROKE},
      {"shortcutsGestureRockerRightLeft",
       IDS_SETTINGS_SHORTCUTS_GESTURE_ROCKER_RIGHT_LEFT},
      {"shortcutsGestureRockerLeftRight",
       IDS_SETTINGS_SHORTCUTS_GESTURE_ROCKER_LEFT_RIGHT},
      {"shortcutsGestureWheelUp", IDS_SETTINGS_SHORTCUTS_GESTURE_WHEEL_UP},
      {"shortcutsGestureWheelDown", IDS_SETTINGS_SHORTCUTS_GESTURE_WHEEL_DOWN},
  };
  html_source->AddLocalizedStrings(kStrings);
}

}  // namespace settings
