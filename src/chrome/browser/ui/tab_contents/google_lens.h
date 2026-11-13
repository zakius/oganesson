// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_TAB_CONTENTS_GOOGLE_LENS_H_
#define CHROME_BROWSER_UI_TAB_CONTENTS_GOOGLE_LENS_H_

#include <memory>

#include "base/check.h"
#include "chrome/common/oganesson_pref_names.h"
#include "components/prefs/pref_service.h"
#include "components/search_engines/template_url.h"
#include "components/search_engines/template_url_data_util.h"
#include "components/search_engines/template_url_prepopulate_data.h"

// The opt-in "Search image with Google Lens" item of an image's context menu
// (Settings > Search engine). Header-only, like oganesson_prefs.h: its two
// callers are in different targets.
namespace google_lens {

// Google's built-in engine. Its image search is Lens's upload page, which
// needs no API key, from prepopulated_engines.json, which domain substitution
// leaves alone.
inline std::unique_ptr<TemplateURL> GoogleEngine() {
  constexpr int kGooglePrepopulateId = 1;
  const auto* engine =
      TemplateURLPrepopulateData::GetPrepopulatedEngineFromBuiltInData(
          kGooglePrepopulateId, {}, {});
  CHECK(engine);
  return std::make_unique<TemplateURL>(
      *TemplateURLDataFromPrepopulatedEngine(*engine));
}

// Whether the menu adds the Lens item: the switch is on, and the default
// engine's own image search item (for `image_search`, null when the engine
// has none) doesn't go to Lens already, as Google's does.
inline bool OfferItem(const PrefService& prefs,
                      const TemplateURL* image_search) {
  if (!prefs.GetBoolean(prefs::kGoogleLensEnabled)) {
    return false;
  }
  return !image_search ||
         image_search->image_url() != GoogleEngine()->image_url();
}

}  // namespace google_lens

#endif  // CHROME_BROWSER_UI_TAB_CONTENTS_GOOGLE_LENS_H_
