// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "third_party/blink/renderer/core/html/oganesson_app_links.h"

#include "mojo/public/cpp/bindings/remote.h"
#include "third_party/blink/public/common/browser_interface_broker_proxy.h"
#include "third_party/blink/public/mojom/manifest/display_mode.mojom-blink.h"
#include "third_party/blink/public/mojom/oganesson/app_link_host.mojom-blink.h"
#include "third_party/blink/renderer/core/css/media_values.h"
#include "third_party/blink/renderer/core/dom/document.h"
#include "third_party/blink/renderer/core/dom/element.h"
#include "third_party/blink/renderer/core/event_type_names.h"
#include "third_party/blink/renderer/core/events/mouse_event.h"
#include "third_party/blink/renderer/core/frame/local_frame.h"
#include "third_party/blink/renderer/core/html_names.h"

namespace blink::oganesson_app_links {

bool MaybeOpenOutsideApp(const Event& event, Node& target) {
  if (!event.isTrusted() || !event.IsMouseEvent() ||
      (event.type() != event_type_names::kClick &&
       event.type() != event_type_names::kAuxclick)) {
    return false;
  }
  const auto& mouse = To<MouseEvent>(event);
  if (mouse.button() != 0 && mouse.button() != 1) {
    return false;
  }
  LocalFrame* frame = target.GetDocument().GetFrame();
  if (!frame || !frame->IsOutermostMainFrame() ||
      !LocalFrame::HasTransientUserActivation(frame)) {
    return false;
  }
  // Tabs show pages in the "browser" display mode, app windows in another:
  // only those ask the browser.
  mojom::blink::DisplayMode mode = MediaValues::CalculateDisplayMode(frame);
  if (mode == mojom::blink::DisplayMode::kBrowser ||
      mode == mojom::blink::DisplayMode::kUndefined) {
    return false;
  }
  Element* link = target.EnclosingLinkEventParentOrSelf();
  if (!link || link->FastHasAttribute(html_names::kDownloadAttr)) {
    return false;
  }
  const KURL url = link->HrefURL();
  if (!url.ProtocolIsInHttpFamily()) {
    return false;
  }
  mojo::Remote<mojom::blink::OganessonAppLinkHost> host;
  frame->GetBrowserInterfaceBroker().GetInterface(
      host.BindNewPipeAndPassReceiver());
  bool opened = false;
  // As Chromium's dispositions: a middle click or Ctrl+click opens a
  // background tab, with Shift a foreground one.
  host->OpenOutsideApp(
      url, (mouse.button() == 1 || mouse.ctrlKey()) && !mouse.shiftKey(),
      &opened);
  return opened;
}

}  // namespace blink::oganesson_app_links
