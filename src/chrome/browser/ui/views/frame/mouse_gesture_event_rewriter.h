// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_VIEWS_FRAME_MOUSE_GESTURE_EVENT_REWRITER_H_
#define CHROME_BROWSER_UI_VIEWS_FRAME_MOUSE_GESTURE_EVENT_REWRITER_H_

#include <memory>

class BrowserView;

// Recognizes right-button mouse gestures on browser-owned Aura surfaces and
// runs the commands prefs::kMouseGestures maps them to. User guide:
// docs/mouse-gestures.md.
//
// It is a ui::EventRewriter on the browser window host's event source, so it
// sees input before targeting, before any renderer or Views control: every
// page, hung or event-cancelling ones included, and the browser's own
// controls get the same gestures. One per browser window.
//
// The right press is held from the start, because Views opens context menus
// on press outside Windows and a page would see the press before the stroke
// is recognized. A click without a stroke is replayed past the rewriter with
// its original coordinates and modifiers (keeping Helium's Shift+right-click
// override), but not its original hit-tested control or document. Strokes
// are dominant-axis directions after 16 DIPs, repeats collapsed, at most 64,
// in root coordinates. On release, state and capture are reset before the
// mapped command is posted, guarded by window lifetime, the cancellation
// generation, the active tab and chrome::IsCommandEnabled(). Escape, lost
// capture, deactivation, window closure, a bounds change or a tab switch
// cancel, and the claimed release is drained so no control gets an unmatched
// release. No gesture starts under pointer lock.
//
// Other platforms need their own hooks: Windows caption right-button messages
// before HWNDMessageHandler opens the system menu, and on macOS a
// window-filtered NSEvent monitor that can swallow claimed events, also for
// fullscreen toolbar and remote Cocoa windows.
class MouseGestureEventRewriter {
 public:
  static std::unique_ptr<MouseGestureEventRewriter> Create(
      BrowserView* browser_view);

  virtual ~MouseGestureEventRewriter() = default;

  // Drops the gesture in progress, if any.
  virtual void Cancel() = 0;

  // Commands fired mid-gesture, such as wheel tab cycling, may switch tabs
  // themselves; any other tab switch cancels the gesture.
  virtual void OnActiveTabChanged() = 0;
};

#endif  // CHROME_BROWSER_UI_VIEWS_FRAME_MOUSE_GESTURE_EVENT_REWRITER_H_
