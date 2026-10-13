// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_COMMON_OGANESSON_PREF_NAMES_H_
#define CHROME_COMMON_OGANESSON_PREF_NAMES_H_

namespace prefs {

// Dictionary mapping mouse gestures, such as the stroke chain "LU" or
// "wheel-up", to a browser command id or to an extension command stored as
// {"extension": id, "command": name}.
inline constexpr char kMouseGestures[] = "oganesson.mouse_gestures";

// A boolean pref set to true if tabs show the icon for audio playing.
inline constexpr char kShowTabAudioIndicator[] =
    "oganesson.tabs.show_audio_indicator";

}  // namespace prefs

#endif  // CHROME_COMMON_OGANESSON_PREF_NAMES_H_
