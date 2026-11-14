// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef COMPONENTS_TRANSLATE_CORE_COMMON_OGANESSON_TRANSLATION_H_
#define COMPONENTS_TRANSLATE_CORE_COMMON_OGANESSON_TRANSLATION_H_

#include <string>

#include "components/prefs/pref_service.h"

// The opt-in page translation (Settings > Languages > Translation), one
// setting for the whole browser in Local State: Helium's TranslationProviders
// are global. Header-only, like oganesson_prefs.h: the translate client, the
// component updater and the Translator API read it, in different targets.
namespace oganesson_translation {

// Whether pages can be translated at all. Off by default (goals.md).
inline constexpr char kEnabledPref[] = "oganesson.translate.enabled";
// The engine: kOnDevice or kGoogle.
inline constexpr char kEnginePref[] = "oganesson.translate.engine";
inline constexpr char kOnDevice[] = "device";
inline constexpr char kGoogle[] = "google";

enum class Engine { kOff, kOnDevice, kGoogle };

// The engine in use, kOff when translation is off or `local_state` is null.
inline Engine GetEngine(const PrefService* local_state) {
  if (!local_state || !local_state->FindPreference(kEnabledPref) ||
      !local_state->GetBoolean(kEnabledPref)) {
    return Engine::kOff;
  }
  return local_state->GetString(kEnginePref) == kGoogle ? Engine::kGoogle
                                                         : Engine::kOnDevice;
}

}  // namespace oganesson_translation

#endif  // COMPONENTS_TRANSLATE_CORE_COMMON_OGANESSON_TRANSLATION_H_
