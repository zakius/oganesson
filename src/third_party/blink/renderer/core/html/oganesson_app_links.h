// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef THIRD_PARTY_BLINK_RENDERER_CORE_HTML_OGANESSON_APP_LINKS_H_
#define THIRD_PARTY_BLINK_RENDERER_CORE_HTML_OGANESSON_APP_LINKS_H_

#include "third_party/blink/public/web/web_frame_load_type.h"

namespace blink {

class FrameLoadRequest;
class KURL;
class LocalFrame;

// In the main frame of an installed web app's window, the page's ways to
// change its address ask the browser first, at their two entry points:
// FrameLoader::StartNavigation (location and its setters, including hash,
// navigation.navigate(), a link's default action, forms, meta refresh) and
// History::StateObjectAdded (pushState, replaceState). A URL that leaves
// the app opens in the default browser instead, and the address doesn't
// change. Tabs don't ask: their pages have the "browser" display mode.
namespace oganesson_app_links {

// For FrameLoader::StartNavigation: whether to drop `request`, a navigation
// of `frame` in place, as its URL left the app.
bool MaybeOpenOutsideApp(LocalFrame& frame,
                         const FrameLoadRequest& request,
                         WebFrameLoadType type);

// For pushState and replaceState: whether to drop the change of `frame`'s
// address to `url`, as it left the app. From a user's input, the page then
// gets a popstate for the entry it is still on.
bool MaybeOpenOutsideApp(LocalFrame& frame, const KURL& url);

}  // namespace oganesson_app_links

}  // namespace blink

#endif  // THIRD_PARTY_BLINK_RENDERER_CORE_HTML_OGANESSON_APP_LINKS_H_
