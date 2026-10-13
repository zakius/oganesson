// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef THIRD_PARTY_BLINK_RENDERER_CORE_HTML_MEDIA_OGANESSON_AUTOPLAY_H_
#define THIRD_PARTY_BLINK_RENDERER_CORE_HTML_MEDIA_OGANESSON_AUTOPLAY_H_

#include "third_party/blink/public/mojom/frame/user_activation_notification_type.mojom-blink-forward.h"

namespace blink {

class Document;
class Frame;
class LocalFrame;

// The Autoplay setting's "Block audio and video" choice, which the browser
// sends as mojom::blink::kAutoplayFlagDocumentInputRequired
// (chrome/browser/content_settings/autoplay_setting.h). AutoplayPolicy asks
// these functions instead of its own rules when RequiresDocumentInput() is
// true. See docs/autoplay.md.
namespace oganesson_autoplay {

// The page's Autoplay setting is "Block audio and video".
bool RequiresDocumentInput(const Document& document);

// AutoplayPolicy::IsDocumentAllowedToPlay() after the force-allow and media
// capture checks: only input in `document` or in an ancestor delegating
// autoplay counts. Not the activation a navigation carries over, media
// engagement or the user exception flag.
bool IsDocumentAllowedToPlay(const Document& document);

// AutoplayPolicy::HasTransientUserActivation(): the transient activation of
// `frame`'s own document, not the opener's, nor what a reused frame keeps from
// the previous document.
bool HasTransientUserActivation(const LocalFrame& frame);

// A user activation reached `frame`'s document: input in it or in a child
// frame, or play from the browser's media controls. Script an extension runs
// or messages it sends don't count, even when they carry the activation of a
// click elsewhere (see the .cc).
void DidReceiveUserActivation(
    Frame& frame,
    mojom::blink::UserActivationNotificationType type);

}  // namespace oganesson_autoplay

}  // namespace blink

#endif  // THIRD_PARTY_BLINK_RENDERER_CORE_HTML_MEDIA_OGANESSON_AUTOPLAY_H_
