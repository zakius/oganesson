// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_VIEWS_FRAME_APP_MODAL_DIALOG_SCOPE_H_
#define CHROME_BROWSER_UI_VIEWS_FRAME_APP_MODAL_DIALOG_SCOPE_H_

class BrowserWindowInterface;

// Whether an app-modal dialog (the beforeunload "Leave this page?" dialog)
// of `dialog_window` leaves `window` usable. Chromium blocks every browser
// window while one shows: BrowserView::CanActivate() refuses activation, and on
// X11 and Wayland JavascriptAppModalEventBlockerAura drops input. An installed
// web app's window is an app of its own, so a dialog in another window doesn't
// block it, and an app's dialog doesn't block other windows. Regular windows
// still block each other. A dialog without a window (an extension's background
// page) blocks every window, as in Chromium.
bool AppModalDialogSparesWindow(const BrowserWindowInterface* dialog_window,
                                const BrowserWindowInterface* window);

#endif  // CHROME_BROWSER_UI_VIEWS_FRAME_APP_MODAL_DIALOG_SCOPE_H_
