// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/content_settings/generated_helium_noise_pref.h"

#include "chrome/browser/content_settings/host_content_settings_map_factory.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/common/extensions/api/settings_private.h"
#include "chrome/common/pref_names.h"

namespace settings_api = extensions::api::settings_private;
using extensions::settings_private::SetPrefResult;

namespace content_settings {

GeneratedHeliumNoisePref::GeneratedHeliumNoisePref(Profile* profile)
    : map_(HostContentSettingsMapFactory::GetForProfile(profile)) {
  observation_.Observe(map_.get());
}

GeneratedHeliumNoisePref::~GeneratedHeliumNoisePref() = default;

void GeneratedHeliumNoisePref::OnContentSettingChanged(
    const ContentSettingsPattern& primary_pattern,
    const ContentSettingsPattern& secondary_pattern,
    ContentSettingsTypeSet content_type_set) {
  if (content_type_set.Contains(ContentSettingsType::HELIUM_NOISE)) {
    NotifyObservers(prefs::kHeliumNoiseEnabled);
  }
}

SetPrefResult GeneratedHeliumNoisePref::SetPref(const base::Value* value) {
  if (!value->is_bool()) {
    return SetPrefResult::PREF_TYPE_MISMATCH;
  }
  map_->SetDefaultContentSetting(
      ContentSettingsType::HELIUM_NOISE,
      value->GetBool() ? CONTENT_SETTING_ALLOW : CONTENT_SETTING_BLOCK);
  return SetPrefResult::SUCCESS;
}

settings_api::PrefObject GeneratedHeliumNoisePref::GetPrefObject() const {
  settings_api::PrefObject pref;
  pref.key = prefs::kHeliumNoiseEnabled;
  pref.type = settings_api::PrefType::kBoolean;
  pref.value = base::Value(
      map_->GetDefaultContentSetting(ContentSettingsType::HELIUM_NOISE) ==
      CONTENT_SETTING_ALLOW);
  return pref;
}

}  // namespace content_settings
