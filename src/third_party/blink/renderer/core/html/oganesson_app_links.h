// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef THIRD_PARTY_BLINK_RENDERER_CORE_HTML_OGANESSON_APP_LINKS_H_
#define THIRD_PARTY_BLINK_RENDERER_CORE_HTML_OGANESSON_APP_LINKS_H_

namespace blink {

class Event;
class Node;

namespace oganesson_app_links {

// For EventDispatcher: a user's click or middle click on an http(s) link in
// the main frame of an installed web app's window goes to the browser before
// the page sees it. If the link leaves the app, the browser opens it in the
// default browser and this returns true: the click is dropped, so the page's
// own handlers, which may draw the linked page before changing the address
// (as Facebook's router does), never run.
bool MaybeOpenOutsideApp(const Event& event, Node& target);

}  // namespace oganesson_app_links

}  // namespace blink

#endif  // THIRD_PARTY_BLINK_RENDERER_CORE_HTML_OGANESSON_APP_LINKS_H_
