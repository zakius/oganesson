// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/browser_shortcuts/oganesson_shortcut_migration.h"

#include <string>

#include "base/feature_list.h"
#include "base/strings/string_number_conversions.h"
#include "base/values.h"
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

// Gives the key to `to` if it is still on `from`: the user may have taken it
// away, or given it to another command.
void MoveKey(BrowserShortcutService& service,
             ui::KeyboardCode key_code,
             int modifiers,
             int from,
             int to) {
  const std::string key =
      AcceleratorToString(ui::Accelerator(key_code, modifiers));
  if (service.FindCommandForAccelerator(key) == from) {
    service.AssignAcceleratorToCommand(to, key);
  }
}

// Takes out of the prefs the keys the user added to or removed from a
// switch-dependent command. No key runs that command now, so the service drops
// them the next time it saves.
base::DictValue TakeCustomKeys(PrefService& prefs, int command_id) {
  const std::string pref_key = base::NumberToString(command_id);
  const base::DictValue* stored =
      prefs.GetDict(prefs::kCustomAccelerators).FindDict(pref_key);
  if (!stored) {
    return base::DictValue();
  }
  base::DictValue keys = stored->Clone();
  ScopedDictPrefUpdate(&prefs, prefs::kCustomAccelerators)->Remove(pref_key);
  return keys;
}

// Adds and removes those keys on the command the switch picked.
void ApplyCustomKeys(BrowserShortcutService& service,
                     const base::DictValue& keys,
                     int command_id) {
  if (const base::ListValue* added = keys.FindList("added")) {
    for (const base::Value& key : *added) {
      if (key.is_string()) {
        service.AssignAcceleratorToCommand(command_id, key.GetString());
      }
    }
  }
  if (const base::ListValue* removed = keys.FindList("removed")) {
    for (const base::Value& key : *removed) {
      if (key.is_string()) {
        service.UnassignAcceleratorFromCommand(command_id, key.GetString());
      }
    }
  }
}

}  // namespace

void MigrateShortcutSwitches(BrowserShortcutService& service,
                             PrefService& prefs) {
  constexpr int kCtrl = ui::EF_CONTROL_DOWN;
  constexpr int kCtrlShift = ui::EF_CONTROL_DOWN | ui::EF_SHIFT_DOWN;
  const base::DictValue copy_or_inspect_keys =
      TakeCustomKeys(prefs, IDC_COPY_OR_INSPECT_SHORTCUT);
  const base::DictValue ctrl_s_keys =
      TakeCustomKeys(prefs, IDC_CTRL_S_SHORTCUT);

  // Ctrl+Shift+C: Copy URL with the switch on (its default), else Inspect.
  const int copy_or_inspect = prefs.GetBoolean(::prefs::kCopyPageUrlShortcut)
                                  ? IDC_COPY_URL
                                  : IDC_DEV_TOOLS_INSPECT;
  MoveKey(service, ui::VKEY_C, kCtrlShift, IDC_COPY_URL, copy_or_inspect);
  ApplyCustomKeys(service, copy_or_inspect_keys, copy_or_inspect);
  prefs.ClearPref(::prefs::kCopyPageUrlShortcut);

  // Ctrl+S: collapse vertical tabs with the switch on (its default) in the
  // vertical layout, else Save page. The switch's default is on, unlike the
  // new default, so it is turned off rather than cleared.
  const bool collapse =
      prefs.GetBoolean(::prefs::kVerticalCollapseShortcut) &&
      prefs.GetInteger(::prefs::kHeliumLayout) ==
          static_cast<int>(HeliumLayoutType::kVertical);
  const int save_or_collapse =
      collapse ? IDC_TOGGLE_VERTICAL_TABS_COLLAPSE : IDC_SAVE_PAGE;
  MoveKey(service, ui::VKEY_S, kCtrl, IDC_SAVE_PAGE, save_or_collapse);
  ApplyCustomKeys(service, ctrl_s_keys, save_or_collapse);
  prefs.SetBoolean(::prefs::kVerticalCollapseShortcut, false);

  // Ctrl+Tab and Ctrl+Shift+Tab: recent order with Helium's switch on, or
  // with Chromium's while its flag is on, else the next and previous tab.
  const bool recent_order =
      prefs.GetBoolean(::prefs::kTabCyclingMRU) ||
      (base::FeatureList::IsEnabled(features::kCtrlTabMru) &&
       prefs.GetBoolean(::prefs::kCtrlTabMru));
  if (recent_order) {
    MoveKey(service, ui::VKEY_TAB, kCtrl, IDC_SELECT_NEXT_TAB,
            IDC_CYCLE_TO_NEXT_TAB);
    MoveKey(service, ui::VKEY_TAB, kCtrlShift, IDC_SELECT_PREVIOUS_TAB,
            IDC_CYCLE_TO_PREV_TAB);
  }
  prefs.ClearPref(::prefs::kTabCyclingMRU);
  prefs.ClearPref(::prefs::kCtrlTabMru);
}

}  // namespace browser_shortcuts
