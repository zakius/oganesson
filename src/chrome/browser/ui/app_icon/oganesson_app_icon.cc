// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/app_icon/oganesson_app_icon.h"

#include <iterator>

#include "base/functional/bind.h"
#include "chrome/common/oganesson_pref_names.h"
#include "components/prefs/pref_change_registrar.h"
#include "components/prefs/pref_service.h"

namespace oganesson_app_icon {

namespace {

PrefChangeRegistrar* g_registrar = nullptr;

void OnPrefChanged(PrefService* local_state) {
  Apply(VariantIndex(local_state->GetString(prefs::kAppIcon)));
}

}  // namespace

size_t VariantIndex(std::string_view name) {
  for (size_t i = 0; i < std::size(kVariants); ++i) {
    if (kVariants[i] == name) {
      return i;
    }
  }
  return 0;
}

void Start(PrefService* local_state) {
  g_registrar = new PrefChangeRegistrar();
  g_registrar->Init(local_state);
  // Local state outlives the registrar: Stop() runs first.
  g_registrar->Add(prefs::kAppIcon,
                   base::BindRepeating(&OnPrefChanged, local_state));
  OnPrefChanged(local_state);
}

void Stop() {
  delete g_registrar;
  g_registrar = nullptr;
}

}  // namespace oganesson_app_icon
