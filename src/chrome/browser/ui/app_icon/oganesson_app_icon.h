// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_APP_ICON_OGANESSON_APP_ICON_H_
#define CHROME_BROWSER_UI_APP_ICON_OGANESSON_APP_ICON_H_

#include <cstddef>
#include <string_view>

#include "build/build_config.h"

#if BUILDFLAG(IS_WIN)
#include <windows.h>
#endif

class PrefService;

namespace gfx {
class ImageSkia;
}

// Settings > Appearance > App icon (docs/app-icon.md): one of the Og icon's
// variants, the same as tennessine's Settings > App icon offers, for the
// browser's windows and, on Linux, its .desktop entry or, on Windows, its
// shortcuts.
namespace oganesson_app_icon {

// The variants, by the name the pref stores. The first is the default: the
// product logo every build carries. tools/branding_icons.py draws each, and
// RegisterOganessonLocalStatePrefs registers the first as the default.
inline constexpr std::string_view kVariants[] = {
    "orange", "teal",        "crimson",    "black",
    "white",  "clear_white", "clear_black"};

// The index in kVariants of `name`, or 0 for a name it doesn't have.
size_t VariantIndex(std::string_view name);

// Follows the pref from now on: sets the chosen icon on the open windows and,
// as the platform has them, on its .desktop entry or shortcuts. Before the
// browser's first window, so it opens with the icon.
void Start(PrefService* local_state);
// Before local state goes.
void Stop();

#if BUILDFLAG(IS_LINUX)
// The chosen icon, for windows as they open, or null for the product logo.
gfx::ImageSkia* GetWindowIcon();
#elif BUILDFLAG(IS_WIN)
// The chosen icon at the system's large or small icon size, for windows as
// they open, or null for the product logo.
HICON GetWindowIcon(bool small_icon);
#endif

// Shows variant `index` on the open windows and, on Linux and Windows, where
// the desktop shows the browser. Each platform's file has it.
void Apply(size_t index);

}  // namespace oganesson_app_icon

#endif  // CHROME_BROWSER_UI_APP_ICON_OGANESSON_APP_ICON_H_
