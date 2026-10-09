// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/webui/settings/shortcut_capture_suspender.h"

#include <map>

#include "base/no_destructor.h"
#include "content/public/browser/web_contents.h"
#include "ui/views/focus/focus_manager.h"

namespace settings {

namespace {

// The settings pages that record a shortcut in each window.
std::map<views::Widget*, int>& RecordingPagesInWindow() {
  static base::NoDestructor<std::map<views::Widget*, int>> recording_pages;
  return *recording_pages;
}

}  // namespace

ShortcutCaptureSuspender::ShortcutCaptureSuspender(
    content::WebContents* web_contents)
    : web_contents_(web_contents) {}

ShortcutCaptureSuspender::~ShortcutCaptureSuspender() {
  SetSuspended(false);
}

void ShortcutCaptureSuspender::SetSuspended(bool suspended) {
  views::Widget* widget =
      suspended ? views::Widget::GetTopLevelWidgetForNativeView(
                      web_contents_->GetNativeView())
                : nullptr;
  if (suspended_widget_.IsObserving()) {
    if (suspended_widget_.GetSource() == widget) {
      return;
    }
    Release();
  }
  if (widget && widget->GetFocusManager()) {
    widget->GetFocusManager()->set_shortcut_handling_suspended(true);
    ++RecordingPagesInWindow()[widget];
    suspended_widget_.Observe(widget);
  }
}

void ShortcutCaptureSuspender::Release() {
  views::Widget* widget = suspended_widget_.GetSource();
  suspended_widget_.Reset();
  auto& recording_pages = RecordingPagesInWindow();
  if (--recording_pages[widget] > 0) {
    return;
  }
  recording_pages.erase(widget);
  if (views::FocusManager* focus_manager = widget->GetFocusManager()) {
    focus_manager->set_shortcut_handling_suspended(false);
  }
}

void ShortcutCaptureSuspender::OnWidgetDestroying(views::Widget* widget) {
  Release();
}

}  // namespace settings
