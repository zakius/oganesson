// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "third_party/blink/renderer/core/html/oganesson_app_links.h"

#include "mojo/public/cpp/bindings/remote.h"
#include "third_party/blink/public/platform/browser_interface_broker_proxy.h"
#include "third_party/blink/public/mojom/manifest/display_mode.mojom-blink.h"
#include "third_party/blink/public/mojom/oganesson/app_link_host.mojom-blink.h"
#include "third_party/blink/renderer/core/frame/local_frame.h"
#include "third_party/blink/renderer/core/loader/frame_load_request.h"
#include "third_party/blink/renderer/core/loader/frame_loader.h"
#include "third_party/blink/renderer/core/loader/frame_loader_types.h"
#include "third_party/blink/renderer/platform/network/http_names.h"
#include "third_party/blink/renderer/platform/widget/frame_widget.h"

namespace blink::oganesson_app_links {

namespace {

// Asks the browser whether `url` leaves the app of `frame`'s window; if it
// does, the browser has it opened in the default browser.
bool LeavesApp(LocalFrame& frame, const KURL& url, bool link) {
  if (!frame.IsOutermostMainFrame() || !url.ProtocolIsInHttpFamily()) {
    return false;
  }
  // The display mode CSS sees, as MediaValues gets it.
  FrameWidget* widget = frame.GetWidgetForLocalRoot();
  mojom::blink::DisplayMode mode =
      widget ? widget->DisplayMode() : mojom::blink::DisplayMode::kBrowser;
  if (mode == mojom::blink::DisplayMode::kBrowser ||
      mode == mojom::blink::DisplayMode::kUndefined) {
    return false;
  }
  const bool activation = LocalFrame::HasTransientUserActivation(&frame);
  mojo::Remote<mojom::blink::OganessonAppLinkHost> host;
  frame.GetBrowserInterfaceBroker().GetInterface(
      host.BindNewPipeAndPassReceiver());
  bool leaves = false;
  host->OpenOutsideApp(url, link && activation, /*background=*/!activation,
                       &leaves);
  return leaves;
}

}  // namespace

bool MaybeOpenOutsideApp(LocalFrame& frame,
                         const FrameLoadRequest& request,
                         WebFrameLoadType type) {
  // A new tab or window goes through the browser's Navigate(), which checks
  // it there. A post's body can't go along to the default browser.
  if (request.GetNavigationPolicy() != kNavigationPolicyCurrentTab ||
      IsReloadLoadType(type) ||
      request.GetResourceRequest().HttpMethod() == http_names::kPOST) {
    return false;
  }
  return LeavesApp(
      frame, request.GetResourceRequest().Url(),
      request.GetClientNavigationReason() == ClientNavigationReason::kAnchorClick);
}

bool MaybeOpenOutsideApp(LocalFrame& frame, const KURL& url) {
  // From a click, as a link's: Facebook's links push their URL.
  return LeavesApp(frame, url, /*link=*/true);
}

}  // namespace blink::oganesson_app_links
