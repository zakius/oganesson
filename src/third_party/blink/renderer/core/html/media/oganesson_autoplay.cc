// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "third_party/blink/renderer/core/html/media/oganesson_autoplay.h"

#include "services/network/public/mojom/permissions_policy/permissions_policy_feature.mojom-blink.h"
#include "third_party/blink/public/mojom/autoplay/autoplay.mojom-blink.h"
#include "third_party/blink/public/mojom/frame/user_activation_notification_type.mojom-blink.h"
#include "third_party/blink/renderer/core/dom/document.h"
#include "third_party/blink/renderer/core/execution_context/execution_context.h"
#include "third_party/blink/renderer/core/frame/local_dom_window.h"
#include "third_party/blink/renderer/core/frame/local_frame.h"
#include "third_party/blink/renderer/core/page/page.h"
#include "third_party/blink/renderer/platform/heap/garbage_collected.h"
#include "third_party/blink/renderer/platform/supplementable.h"

namespace blink::oganesson_autoplay {

namespace {

// Present on a window once its document received user input. Unlike the
// frame's sticky activation, a new document doesn't inherit it: Chromium keeps
// the activation (sticky, and transient on a reused frame) across same-origin
// navigations.
class DocumentInput final : public GarbageCollected<DocumentInput>,
                            public Supplement<LocalDOMWindow> {
 public:
  static constexpr char kSupplementName[] = "OganessonDocumentInput";
  explicit DocumentInput(LocalDOMWindow& window) : Supplement(window) {}
  void Trace(Visitor* visitor) const override { Supplement::Trace(visitor); }
};

bool HadDocumentInput(const Frame& frame) {
  const auto* local_frame = DynamicTo<LocalFrame>(frame);
  // ponytail: a frame in another process (the parent of an out-of-process
  // iframe) counts with its replicated sticky activation, which a same-origin
  // navigation keeps. Replicate the input mark too if that matters.
  if (!local_frame) {
    return frame.HasStickyUserActivation();
  }
  return local_frame->DomWindow() &&
         Supplement<LocalDOMWindow>::From<DocumentInput>(
             local_frame->DomWindow());
}

}  // namespace

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
  return LocalFrame::HasTransientUserActivation(&frame) &&
         HadDocumentInput(frame);
}

void DidReceiveUserActivation(
    Frame& frame,
    mojom::blink::UserActivationNotificationType type) {
  // An extension holds the activation of a click in a page for 5 s and passes
  // it on with the script it injects and the messages it sends. uBlock Origin
  // injects its scriptlets into the tab a middle-click opens on YouTube with
  // the click's activation, which isn't input in that page.
  using Type = mojom::blink::UserActivationNotificationType;
  switch (type) {
    case Type::kExtensionEvent:
    case Type::kExtensionGuestView:
    case Type::kExtensionMessaging:
    case Type::kExtensionMessagingBothPrivileged:
    case Type::kExtensionMessagingSenderPrivileged:
    case Type::kExtensionMessagingReceiverPrivileged:
    case Type::kExtensionMessagingNeitherPrivileged:
    case Type::kWebScriptExec:
    case Type::kActorWebMCP:
      return;
    default:
      break;
  }
  auto* local_frame = DynamicTo<LocalFrame>(frame);
  LocalDOMWindow* window = local_frame ? local_frame->DomWindow() : nullptr;
  if (window && !Supplement<LocalDOMWindow>::From<DocumentInput>(window)) {
    Supplement<LocalDOMWindow>::ProvideTo(
        *window, MakeGarbageCollected<DocumentInput>(*window));
  }
}

}  // namespace blink::oganesson_autoplay
