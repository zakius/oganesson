// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/views/frame/app_modal_dialog_scope.h"

#include "chrome/browser/ui/web_applications/app_browser_controller.h"

bool AppModalDialogSparesWindow(const BrowserWindowInterface* dialog_window,
                                const BrowserWindowInterface* window) {
  return dialog_window && window && dialog_window != window &&
         (web_app::AppBrowserController::IsWebApp(dialog_window) ||
          web_app::AppBrowserController::IsWebApp(window));
}
