// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/web_applications/web_install_request.h"

#include <utility>

#include "base/no_destructor.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/browser/web_contents.h"

namespace web_app {

namespace {

base::RepeatingCallbackList<void(content::WebContents*)>& ChangedCallbacks() {
  static base::NoDestructor<
      base::RepeatingCallbackList<void(content::WebContents*)>>
      callbacks;
  return *callbacks;
}

}  // namespace

WebInstallRequest::WebInstallRequest(content::WebContents* web_contents)
    : content::WebContentsUserData<WebInstallRequest>(*web_contents),
      content::WebContentsObserver(web_contents) {}

WebInstallRequest::~WebInstallRequest() = default;

// static
void WebInstallRequest::Store(content::RenderFrameHost& frame,
                              base::OnceClosure install) {
  if (!frame.IsInPrimaryMainFrame()) {
    return;
  }
  content::WebContents* web_contents =
      content::WebContents::FromRenderFrameHost(&frame);
  CreateForWebContents(web_contents);
  FromWebContents(web_contents)->install_ = std::move(install);
  ChangedCallbacks().Notify(web_contents);
}

// static
bool WebInstallRequest::Has(content::WebContents* web_contents) {
  WebInstallRequest* request = FromWebContents(web_contents);
  return request && request->install_ && !request->install_.IsCancelled();
}

// static
bool WebInstallRequest::Run(content::WebContents* web_contents) {
  if (!Has(web_contents)) {
    return false;
  }
  base::OnceClosure install =
      std::exchange(FromWebContents(web_contents)->install_, {});
  ChangedCallbacks().Notify(web_contents);
  std::move(install).Run();
  return true;
}

// static
base::CallbackListSubscription WebInstallRequest::RegisterChanged(
    ChangedCallback callback) {
  return ChangedCallbacks().Add(std::move(callback));
}

void WebInstallRequest::PrimaryPageChanged(content::Page& page) {
  Drop();
}

void WebInstallRequest::PrimaryMainFrameRenderProcessGone(
    base::TerminationStatus status) {
  Drop();
}

void WebInstallRequest::Drop() {
  if (install_) {
    install_.Reset();
    ChangedCallbacks().Notify(web_contents());
  }
}

WEB_CONTENTS_USER_DATA_KEY_IMPL(WebInstallRequest);

}  // namespace web_app
