// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_MIGRATION_H_
#define CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_MIGRATION_H_

#include <string>

#include "base/memory/raw_ref.h"
#include "base/values.h"

class PrefService;

namespace browser_shortcuts {

class BrowserShortcutService;

// Ctrl+Shift+C, Ctrl+S and Ctrl+Tab used to run one of two commands, picked
// by a settings switch. Now each command has its own row on the Shortcuts
// page. Where a profile's switch picked another command than the new
// defaults do, that command gets the keys as key assignments, so the keys
// keep doing what they did. Each switch is then set to the new defaults'
// value, so this changes a profile only once.
class ShortcutSwitchMigration {
 public:
  // Takes the keys the user added to or removed from the switch-dependent
  // commands out of the prefs. Construct it before the service loads its
  // prefs: no key runs those commands now, so loading drops them.
  explicit ShortcutSwitchMigration(PrefService& prefs);
  ~ShortcutSwitchMigration();

  // Moves the keys on the loaded service.
  void Run(BrowserShortcutService& service);

 private:
  // A key that ran a switch-dependent command, and what the user changed.
  struct OldKey {
    std::string key;
    // The command's "added" and "removed" keys from the prefs.
    base::DictValue custom;
    // The user gave the key to another command.
    bool given_to_another = false;
  };

  OldKey TakeOldKey(int command_id, std::string key);
  void MoveOldKey(BrowserShortcutService& service,
                  const OldKey& old,
                  int new_default,
                  int to);

  const raw_ref<PrefService> prefs_;
  OldKey copy_or_inspect_;
  OldKey ctrl_s_;
};

}  // namespace browser_shortcuts

#endif  // CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_MIGRATION_H_
