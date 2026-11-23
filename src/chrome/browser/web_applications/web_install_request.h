// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_WEB_APPLICATIONS_WEB_INSTALL_REQUEST_H_
#define CHROME_BROWSER_WEB_APPLICATIONS_WEB_INSTALL_REQUEST_H_

#include "base/callback_list.h"
#include "base/functional/callback.h"
#include "content/public/browser/web_contents_observer.h"
#include "content/public/browser/web_contents_user_data.h"

namespace content {
class Page;
class WebContents;
}  // namespace content

namespace web_app {

// A site's navigator.install() call shows no dialog. Its install waits here,
// on the tab, until the user clicks the address bar's install icon, which has
// a badge meanwhile (chrome/browser/ui/web_applications/web_install_badge.h).
// The tab keeps one request, the last; a new page drops it.
class WebInstallRequest
    : public content::WebContentsUserData<WebInstallRequest>,
      public content::WebContentsObserver {
 public:
  using ChangedCallback = base::RepeatingCallback<void(content::WebContents*)>;

  ~WebInstallRequest() override;

  // Keeps `install` as the request of `web_contents`, in place of the one
  // before.
  static void Store(content::WebContents* web_contents,
                    base::OnceClosure install);

  // Whether `web_contents` has a request that can still run.
  static bool Has(content::WebContents* web_contents);

  // Drops the request of `web_contents` and runs it. False if there was none.
  static bool Run(content::WebContents* web_contents);

  // `callback` runs with a tab's contents when its request comes or goes.
  static base::CallbackListSubscription RegisterChanged(
      ChangedCallback callback);

  // content::WebContentsObserver:
  void PrimaryPageChanged(content::Page& page) override;

 private:
  friend class content::WebContentsUserData<WebInstallRequest>;

  explicit WebInstallRequest(content::WebContents* web_contents);

  base::OnceClosure install_;

  WEB_CONTENTS_USER_DATA_KEY_DECL();
};

}  // namespace web_app

#endif  // CHROME_BROWSER_WEB_APPLICATIONS_WEB_INSTALL_REQUEST_H_
