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
// start now. Not when on-device translation would first download TranslateKit
// or language packs: then this asks the user, returns false, and runs
// `translate` once the user agrees to the download.
bool ConfirmDownload(content::WebContents* web_contents,
                     std::string_view source_lang,
                     std::string_view target_lang,
                     base::OnceClosure translate);

}  // namespace oganesson_translation

#endif  // CHROME_BROWSER_TRANSLATE_OGANESSON_TRANSLATION_PROVIDERS_H_
