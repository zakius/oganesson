# Product scope

Linux x86-64 first. Keep mouse gestures, movable toolbar items, full Chromium uBlock Origin, hidden tab close buttons, middle-click on empty tab-bar space to open a tab, Firefox tab placement and close selection, Firefox Sync, and installed web app (PWA) controls: out-of-scope links open in the default browser, per-app scope rules, and a per-app start address.

Keep Chromium's existing extension support and Helium's Manifest V2/uBO maintenance. General Firefox add-on emulation, XPI installation, containers, translation additions, Firefox theme APIs, and unrelated visual changes are outside this fork's scope.

The separate search bar supports the retained toolbar implementation. Bookmark keywords and separators support Firefox Sync without discarding Firefox bookmark structure. These dependencies are explicit rather than a reason to import further features.

Firefox tab rules are the default. Existing preference controls may remain when retaining them is simpler than maintaining a separate implementation. User data uses an isolated profile until migration has dedicated validation.
