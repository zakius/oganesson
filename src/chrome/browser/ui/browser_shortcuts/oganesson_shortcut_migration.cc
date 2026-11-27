// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/browser_shortcuts/oganesson_shortcut_migration.h"

#include <algorithm>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "base/feature_list.h"
#include "base/strings/string_number_conversions.h"
#include "chrome/app/chrome_command_ids.h"
#include "chrome/browser/ui/browser_shortcuts/browser_shortcut_prefs.h"
#include "chrome/browser/ui/browser_shortcuts/browser_shortcut_serialization.h"
#include "chrome/browser/ui/browser_shortcuts/browser_shortcut_service.h"
#include "chrome/browser/ui/helium/helium_layout_state_controller.h"
#include "chrome/browser/ui/ui_features.h"
#include "chrome/common/pref_names.h"
#include "components/prefs/pref_service.h"
#include "components/prefs/scoped_user_pref_update.h"
#include "ui/base/accelerators/accelerator.h"
#include "ui/events/event_constants.h"
#include "ui/events/keycodes/keyboard_codes.h"

namespace browser_shortcuts {

namespace {

constexpr char kAdded[] = "added";
constexpr char kRemoved[] = "removed";

bool ListHas(const base::ListValue* list, std::string_view key) {
  return list && std::ranges::find(*list, base::Value(key)) != list->end();
}

// Gives every key of `from` to `to`.
void MoveAllKeys(BrowserShortcutService& service, int from, int to) {
  std::vector<std::string> keys;
  for (const CommandInfo& command : service.GetCommands()) {
    if (command.command_id != from) {
      continue;
    }
    for (const ShortcutInfo& accelerator : command.accelerators) {
      if (accelerator.user_modifiable) {
        keys.push_back(accelerator.serialized);
      }
    }
  }
  for (const std::string& key : keys) {
    service.AssignAcceleratorToCommand(to, key);
  }
}

}  // namespace

ShortcutSwitchMigration::ShortcutSwitchMigration(PrefService& prefs)
    : prefs_(prefs),
      copy_or_inspect_(TakeOldKey(
          IDC_COPY_OR_INSPECT_SHORTCUT,
          AcceleratorToString(ui::Accelerator(
              ui::VKEY_C, ui::EF_CONTROL_DOWN | ui::EF_SHIFT_DOWN)))),
      ctrl_s_(TakeOldKey(
          IDC_CTRL_S_SHORTCUT,
          AcceleratorToString(ui::Accelerator(ui::VKEY_S,
                                              ui::EF_CONTROL_DOWN)))) {}

ShortcutSwitchMigration::~ShortcutSwitchMigration() = default;

ShortcutSwitchMigration::OldKey ShortcutSwitchMigration::TakeOldKey(
    int command_id,
    std::string key) {
  OldKey old;
  old.key = std::move(key);
  const std::string pref_key = base::NumberToString(command_id);
  const base::DictValue& all = prefs_->GetDict(prefs::kCustomAccelerators);
  for (auto [other_key, other] : all) {
    if (other_key != pref_key && other.is_dict() &&
        ListHas(other.GetDict().FindList(kAdded), old.key)) {
      old.given_to_another = true;
    }
  }
  if (const base::DictValue* custom = all.FindDict(pref_key)) {
    old.custom = custom->Clone();
    ScopedDictPrefUpdate(&prefs_.get(), prefs::kCustomAccelerators)
        ->Remove(pref_key);
  }
  return old;
}

void ShortcutSwitchMigration::MoveOldKey(BrowserShortcutService& service,
                                         const OldKey& old,
                                         int new_default,
                                         int to) {
  if (!ListHas(old.custom.FindList(kRemoved), old.key)) {
    // The key ran the old command. The new defaults give it to `new_default`,
    // which is also where it stays once the switch is reset.
    if (to != new_default) {
      service.AssignAcceleratorToCommand(to, old.key);
    }
  } else if (!old.given_to_another) {
    // The user took the key away.
    service.UnassignAcceleratorFromCommand(new_default, old.key);
  }
  // Otherwise the service has it where the user put it.
  if (const base::ListValue* added = old.custom.FindList(kAdded)) {
    for (const base::Value& key : *added) {
      if (key.is_string()) {
        service.AssignAcceleratorToCommand(to, key.GetString());
      }
    }
  }
}

void ShortcutSwitchMigration::Run(BrowserShortcutService& service) {
  PrefService& prefs = *prefs_;

  // Ctrl+Shift+C: Copy URL with the switch on (its default), else Inspect.
  MoveOldKey(service, copy_or_inspect_, IDC_COPY_URL,
             prefs.GetBoolean(::prefs::kCopyPageUrlShortcut)
                 ? IDC_COPY_URL
                 : IDC_DEV_TOOLS_INSPECT);
  prefs.ClearPref(::prefs::kCopyPageUrlShortcut);

  // Ctrl+S: collapse vertical tabs with the switch on (its default) in the
  // vertical layout, else Save page. The switch's default is on, unlike the
  // new default, so it is turned off rather than cleared.
  const bool collapse =
      prefs.GetBoolean(::prefs::kVerticalCollapseShortcut) &&
      prefs.GetInteger(::prefs::kHeliumLayout) ==
          static_cast<int>(HeliumLayoutType::kVertical);
  MoveOldKey(service, ctrl_s_, IDC_SAVE_PAGE,
             collapse ? IDC_TOGGLE_VERTICAL_TABS_COLLAPSE : IDC_SAVE_PAGE);
  prefs.SetBoolean(::prefs::kVerticalCollapseShortcut, false);

  // Recent order, with Helium's switch on or Chromium's while its flag is on,
  // was what every key of Next tab and Previous tab ran.
  const bool recent_order =
      prefs.GetBoolean(::prefs::kTabCyclingMRU) ||
      (base::FeatureList::IsEnabled(features::kCtrlTabMru) &&
       prefs.GetBoolean(::prefs::kCtrlTabMru));
  if (recent_order) {
    MoveAllKeys(service, IDC_SELECT_NEXT_TAB, IDC_CYCLE_TO_NEXT_TAB);
    MoveAllKeys(service, IDC_SELECT_PREVIOUS_TAB, IDC_CYCLE_TO_PREV_TAB);
  }
  prefs.ClearPref(::prefs::kTabCyclingMRU);
  prefs.ClearPref(::prefs::kCtrlTabMru);
}

}  // namespace browser_shortcuts
