// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_TRANSLATE_OGANESSON_TRANSLATION_PROVIDERS_H_
#define CHROME_BROWSER_TRANSLATE_OGANESSON_TRANSLATION_PROVIDERS_H_

#include <string_view>

#include "base/functional/callback_forward.h"

namespace content {
class WebContents;
}

// The two engines of the opt-in page translation (oganesson_translation.h),
// as TranslationProviders for Helium's translation chain: on this device with
// Chromium's TranslateKit, or with Google Translate's keyless endpoint.
// docs/translation.md.
namespace oganesson_translation {

// Registers both providers. Each is available only while the setting picks
// it. Before profiles are created, as Helium's API asks.
void RegisterProviders();

// Whether translating `web_contents` from `source_lang` to `target_lang` can
// start now. Not when on-device translation needs TranslateKit or language
// packs that aren't installed: then this returns false, and runs `translate`
// once they are, if the tab still shows the same page. A translation the user
// asked for asks before downloading; an automatic one only waits for a
// download already agreed to, or doesn't happen.
bool ConfirmDownload(content::WebContents* web_contents,
                     std::string_view source_lang,
                     std::string_view target_lang,
                     bool asked_by_user,
                     base::OnceClosure translate);

}  // namespace oganesson_translation

#endif  // CHROME_BROWSER_TRANSLATE_OGANESSON_TRANSLATION_PROVIDERS_H_
