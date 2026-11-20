// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "third_party/blink/renderer/core/html/media/oganesson_autoplay.h"

#include "services/network/public/mojom/permissions_policy/permissions_policy_feature.mojom-blink.h"
#include "third_party/blink/public/mojom/autoplay/autoplay.mojom-blink.h"
#include "third_party/blink/renderer/core/dom/document.h"
#include "third_party/blink/renderer/core/execution_context/execution_context.h"
#include "third_party/blink/renderer/core/frame/local_frame.h"
#include "third_party/blink/renderer/core/html/document_input.h"
#include "third_party/blink/renderer/core/page/page.h"

namespace blink::oganesson_autoplay {

bool HadDocumentInput(const Frame& frame) {
  const auto* local_frame = DynamicTo<LocalFrame>(frame);
  // ponytail: a frame in another process (the parent of an out-of-process
  // iframe) counts with its replicated sticky activation, which a same-origin
  // navigation keeps. Replicate the input mark too if that matters.
  if (!local_frame) {
    return frame.HasStickyUserActivation();
  }
  return document_input::HadInput(*local_frame);
}

bool RequiresDocumentInput(const Document& document) {
  return document.GetPage() &&
         (document.GetPage()->AutoplayFlags() &
          mojom::blink::kAutoplayFlagDocumentInputRequired);
}

bool IsDocumentAllowedToPlay(const Document& document) {
  if (!document.GetFrame()) {
    return false;
  }

  bool permissions_policy_enabled =
      document.GetExecutionContext()->IsFeatureEnabled(
          network::mojom::PermissionsPolicyFeature::kAutoplay);

  for (Frame* frame = document.GetFrame(); frame;
       frame = frame->Tree().Parent()) {
    if (HadDocumentInput(*frame)) {
      return true;
    }
    if (!permissions_policy_enabled) {
      return false;
    }
  }
  return false;
}

bool HasTransientUserActivation(const LocalFrame& frame) {
  return document_input::HasTransientUserActivation(frame);
}

}  // namespace blink::oganesson_autoplay
