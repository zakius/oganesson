// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "third_party/blink/renderer/core/html/oganesson_app_links.h"

#include "base/task/single_thread_task_runner.h"
#include "mojo/public/cpp/bindings/remote.h"
#include "third_party/blink/public/platform/browser_interface_broker_proxy.h"
#include "third_party/blink/public/platform/task_type.h"
#include "third_party/blink/public/mojom/manifest/display_mode.mojom-blink.h"
#include "third_party/blink/public/mojom/oganesson/app_link_host.mojom-blink.h"
#include "third_party/blink/renderer/bindings/core/v8/serialization/serialized_script_value.h"
#include "third_party/blink/renderer/core/dom/document.h"
#include "third_party/blink/renderer/core/frame/local_dom_window.h"
#include "third_party/blink/renderer/core/frame/local_frame.h"
#include "third_party/blink/renderer/core/loader/document_loader.h"
#include "third_party/blink/renderer/core/loader/frame_load_request.h"
#include "third_party/blink/renderer/core/loader/frame_loader.h"
#include "third_party/blink/renderer/core/loader/frame_loader_types.h"
#include "third_party/blink/renderer/core/loader/history_item.h"
#include "third_party/blink/renderer/platform/heap/persistent.h"
#include "third_party/blink/renderer/platform/network/http_names.h"
#include "third_party/blink/renderer/platform/wtf/functional.h"
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

// Whether DispatchPopstate's event is being dispatched: renderer main thread
// only.
bool g_in_popstate = false;

// A popstate for the entry `window` is still on, as Back would fire.
void DispatchPopstate(LocalDOMWindow* window) {
  if (!window || !window->GetFrame()) {
    return;
  }
  DocumentLoader* loader = window->document()->Loader();
  HistoryItem* item = loader ? loader->GetHistoryItem() : nullptr;
  g_in_popstate = true;
  window->DispatchPopstateEvent(
      item ? item->StateObject() : SerializedScriptValue::NullValue(),
      /*has_ua_visual_transition=*/false, UserNavigationInvolvement::kNone);
  g_in_popstate = false;
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
  if (!LeavesApp(frame, url, /*link=*/true)) {
    return false;
  }
  // A router that draws the URL's page before it pushes it (Facebook's
  // photo viewer) would show that page in the window, and on closing it go
  // Back past an entry that never existed. A popstate for the entry the page
  // is still on has it draw that entry again, as after Back. Only from a
  // click, and not for a push from that popstate's handler, so a router that
  // pushes again there doesn't loop.
  if (LocalFrame::HasTransientUserActivation(&frame) && !g_in_popstate) {
    LocalDOMWindow* window = frame.DomWindow();
    window->GetTaskRunner(TaskType::kDOMManipulation)
        ->PostTask(FROM_HERE,
                   BindOnce(&DispatchPopstate, WrapWeakPersistent(window)));
  }
  return true;
}

}  // namespace blink::oganesson_app_links
