// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_MIGRATION_H_
#define CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_MIGRATION_H_

class PrefService;

namespace browser_shortcuts {

class BrowserShortcutService;

// Ctrl+Shift+C, Ctrl+S and Ctrl+Tab used to run one of two commands, picked
// by a settings switch. Now each command has its own row on the Shortcuts
// page. Where a profile's switch picked another command than the new
// defaults do, that command gets the key as a key assignment, so the key
// keeps doing what it did. Each switch is then set to the new defaults'
// value, so this changes a profile only once.
void MigrateShortcutSwitches(BrowserShortcutService& service,
                             PrefService& prefs);

}  // namespace browser_shortcuts

#endif  // CHROME_BROWSER_UI_BROWSER_SHORTCUTS_OGANESSON_SHORTCUT_MIGRATION_H_
