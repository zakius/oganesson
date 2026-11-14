// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef COMPONENTS_COMPONENT_UPDATER_TRANSLATE_KIT_GATE_H_
#define COMPONENTS_COMPONENT_UPDATER_TRANSLATE_KIT_GATE_H_

#include <string>
#include <string_view>

#include "base/containers/flat_set.h"
#include "base/no_destructor.h"
#include "components/browser_traffic/browser_traffic.h"
#include "components/translate/core/common/oganesson_translation.h"

// The TranslateKit components, the on-device translation engine and its
// language packs, are the one exception to Helium's component allowlist.
// Chromium registers them when on-device translation first needs them, which
// only the opt-in engine and the Translator API do while it is on
// (oganesson_translation.h). They check for updates at Google's update server,
// on demand and with the automatic checks, only while it is on: once it is off,
// installed packs stay and nothing asks for their updates. Header-only: the
// component installer, the update service and the configurator use it.
namespace component_updater::translate_kit {

// Every TranslateKit installer's name starts with this.
inline bool IsTranslateKit(std::string_view installer_name) {
  return installer_name.starts_with("Chrome TranslateKit");
}

// The crx ids of the TranslateKit components registered so far.
inline base::flat_set<std::string>& RegisteredIds() {
  static base::NoDestructor<base::flat_set<std::string>> ids;
  return *ids;
}

// Whether component `id` is TranslateKit's and may check for an update now.
inline bool MayUpdate(const std::string& id) {
  return RegisteredIds().contains(id) &&
         oganesson_translation::GetEngine(browser_traffic::GetLocalState()) ==
             oganesson_translation::Engine::kOnDevice;
}

}  // namespace component_updater::translate_kit

#endif  // COMPONENTS_COMPONENT_UPDATER_TRANSLATE_KIT_GATE_H_
