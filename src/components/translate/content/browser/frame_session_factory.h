// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef COMPONENTS_TRANSLATE_CONTENT_BROWSER_FRAME_SESSION_FACTORY_H_
#define COMPONENTS_TRANSLATE_CONTENT_BROWSER_FRAME_SESSION_FACTORY_H_

#include <memory>

#include "base/functional/callback.h"
#include "base/no_destructor.h"
#include "components/translate/core/browser/translation_provider.h"

namespace content {
class RenderFrameHost;
}

namespace translate {

// oganesson: starts a provider's session for a frame, so a session that sends
// page text can use the frame's own network context (its profile, container or
// incognito state, and an extension's proxy). Set once at startup
// (oganesson_translation_providers.cc). Unset, TextTranslatorHost calls
// TranslationProvider::StartSession.
using FrameSessionFactory =
    base::RepeatingCallback<std::unique_ptr<TranslationSession>(
        TranslationProvider& provider,
        content::RenderFrameHost& frame)>;

inline FrameSessionFactory& GetFrameSessionFactory() {
  static base::NoDestructor<FrameSessionFactory> factory;
  return *factory;
}

}  // namespace translate

#endif  // COMPONENTS_TRANSLATE_CONTENT_BROWSER_FRAME_SESSION_FACTORY_H_
