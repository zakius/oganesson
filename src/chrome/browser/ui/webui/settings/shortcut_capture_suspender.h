// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_WEBUI_SETTINGS_SHORTCUT_CAPTURE_SUSPENDER_H_
#define CHROME_BROWSER_UI_WEBUI_SETTINGS_SHORTCUT_CAPTURE_SUSPENDER_H_

#include "base/memory/raw_ptr.h"
#include "base/scoped_observation.h"
#include "ui/views/widget/widget.h"
#include "ui/views/widget/widget_observer.h"

namespace content {
class WebContents;
}

namespace settings {

// Reserved shortcuts such as Ctrl+T and Ctrl+W run before a page sees the
// key, so the shortcuts page suspends its window's shortcut handling while it
// records one (#24). Several settings pages of one window may record at once;
// the window's shortcuts resume when the last one stops, or goes away.
class ShortcutCaptureSuspender : public views::WidgetObserver {
 public:
  explicit ShortcutCaptureSuspender(content::WebContents* web_contents);
  ShortcutCaptureSuspender(const ShortcutCaptureSuspender&) = delete;
  ShortcutCaptureSuspender& operator=(const ShortcutCaptureSuspender&) =
      delete;
  ~ShortcutCaptureSuspender() override;

  void SetSuspended(bool suspended);

  // views::WidgetObserver:
  void OnWidgetDestroying(views::Widget* widget) override;

 private:
  // Stops observing the suspended window, and resumes its shortcuts unless
  // another page still records there.
  void Release();

  raw_ptr<content::WebContents> web_contents_;
  // The window whose shortcuts are suspended, resumed when the page asks,
  // goes away or is gone, even if the tab moved to another window since.
  base::ScopedObservation<views::Widget, views::WidgetObserver>
      suspended_widget_{this};
};

}  // namespace settings

#endif  // CHROME_BROWSER_UI_WEBUI_SETTINGS_SHORTCUT_CAPTURE_SUSPENDER_H_
