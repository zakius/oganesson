# App icon

Settings > Appearance > App icon chooses one of the Og icon's variants, the same ones tennessine's Settings > App icon offers:

| Value | Icon |
|---|---|
| `orange` | the white glyph on an orange (#C2410C) rounded square, the default |
| `teal` | the white glyph on teal (#1F5C63) |
| `crimson` | the white glyph on crimson (#7A1F3D) |
| `black` | the white glyph on black |
| `white` | the black glyph on white |
| `clear_white` | the white glyph, no background |
| `clear_black` | the black glyph, no background |

The choice is `oganesson.app_icon` in Local State, so it holds for every profile. `tools/branding_icons.py` draws the variants from `tools/og.svg`. The code is in `src/chrome/browser/ui/app_icon`, wired in by `patches/oganesson/core/app-icon.patch`.

## Linux

The package carries each variant as a 256 px PNG in `app_icons/`, next to the binary (`/opt/oganesson/app_icons` for the .deb and .rpm).

- **Windows**: open browser windows change at once, and new ones open with the chosen icon. X11 window managers and Wayland compositors with `xdg-toplevel-icon` (KDE Plasma) show it.
- **Docks and app menus** (GNOME, KDE, Cinnamon, XFCE) show the icon of the browser's .desktop entry. For a variant other than orange, the browser writes a copy of the installed `oganesson.desktop` to `~/.local/share/applications/` (`$XDG_DATA_HOME/applications`), with `Icon=` naming the variant's PNG. That folder comes before the system's, so the copy replaces the installed entry. Its first line marks it as the browser's; a file there without that line is the user's own, and the browser leaves it alone. Choosing orange again deletes the copy.
- The copy has `TryExec=` set to the entry's program, so menus hide it once the browser is uninstalled. The browser rewrites it at each start, so a package update's changes to the installed entry reach it.
- An unpacked archive has no installed entry to copy, so only its windows change.

## Windows

`chrome.exe` carries the variants as icons 7 to 12, after Chromium's own (`chrome_exe.rc`). A shortcut's Change Icon dialog lists them too.

- **Windows**: open browser windows change at once, and new ones open with the chosen icon.
- **Shortcuts**: the browser points its shortcuts on the desktop, in the Start menu and pinned to the taskbar at the chosen icon in `chrome.exe`. The taskbar shows a pinned browser with its shortcut's icon. It changes only shortcuts that start the browser with no arguments: profile and web app shortcuts keep theirs. An all-users install's shared shortcuts change only when the browser runs with admin rights.
- The installer makes its shortcuts with the default icon. The browser sets them again at its next start.
