// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef THIRD_PARTY_BLINK_RENDERER_CORE_HTML_MEDIA_OGANESSON_AUTOPLAY_H_
#define THIRD_PARTY_BLINK_RENDERER_CORE_HTML_MEDIA_OGANESSON_AUTOPLAY_H_

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

// `frame`'s document received user input: the sticky activation that Block
// audio counts in place of the frame's, which an extension's script or
// message can also set (dubna's document_input.h).
bool HadDocumentInput(const Frame& frame);

// AutoplayPolicy::IsDocumentAllowedToPlay() after the force-allow and media
// capture checks: only input in `document` or in an ancestor delegating
// autoplay counts. Not the activation a navigation carries over, media
// engagement or the user exception flag.
bool IsDocumentAllowedToPlay(const Document& document);

// AutoplayPolicy::HasTransientUserActivation(): the transient activation of
// `frame`'s own document, not the opener's, nor what a reused frame keeps from
// the previous document, and only once the document had input. Block audio
// uses it for the frame's own activation too.
bool HasTransientUserActivation(const LocalFrame& frame);

}  // namespace oganesson_autoplay

}  // namespace blink

#endif  // THIRD_PARTY_BLINK_RENDERER_CORE_HTML_MEDIA_OGANESSON_AUTOPLAY_H_
