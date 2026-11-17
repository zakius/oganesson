// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_CONTENT_SETTINGS_GENERATED_HELIUM_NOISE_PREF_H_
#define CHROME_BROWSER_CONTENT_SETTINGS_GENERATED_HELIUM_NOISE_PREF_H_

#include "base/memory/raw_ptr.h"
#include "base/scoped_observation.h"
#include "chrome/browser/extensions/api/settings_private/generated_pref.h"
#include "components/content_settings/core/browser/content_settings_observer.h"
#include "components/content_settings/core/browser/host_content_settings_map.h"

class Profile;

namespace content_settings {

// Fingerprinting protection's global switch, as Settings shows it under its
// pref's name (helium.noise.enabled): on when HELIUM_NOISE's default is ALLOW.
// The default, not the pref, decides, so a site's own rule wins over the
// switch both ways: a site can have the protection while it is off for all
// others. helium_noise_settings.cc moves a pref turned on before over once.
class GeneratedHeliumNoisePref
    : public content_settings::Observer,
      public extensions::settings_private::GeneratedPref {
 public:
  explicit GeneratedHeliumNoisePref(Profile* profile);
  ~GeneratedHeliumNoisePref() override;

  // content_settings::Observer:
  void OnContentSettingChanged(
      const ContentSettingsPattern& primary_pattern,
      const ContentSettingsPattern& secondary_pattern,
      ContentSettingsTypeSet content_type_set) override;

  // GeneratedPref:
  extensions::settings_private::SetPrefResult SetPref(
      const base::Value* value) override;
  extensions::api::settings_private::PrefObject GetPrefObject() const override;

 private:
  raw_ptr<HostContentSettingsMap> map_;
  base::ScopedObservation<HostContentSettingsMap, content_settings::Observer>
      observation_{this};
};

}  // namespace content_settings

#endif  // CHROME_BROWSER_CONTENT_SETTINGS_GENERATED_HELIUM_NOISE_PREF_H_
