// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/views/tabs/oganesson_tab_close_buttons.h"

#include <memory>

#include "base/functional/bind.h"
#include "base/supports_user_data.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface_iterator.h"
#include "chrome/common/oganesson_pref_names.h"
#include "components/prefs/pref_change_registrar.h"
#include "components/prefs/pref_service.h"
#include "ui/base/base_window.h"
#include "ui/views/view.h"
#include "ui/views/widget/widget.h"

namespace {

const char kWatcherKey[] = "OganessonTabCloseButtonsWatcher";

// A tab decides whether to show its close button when it lays out, so every
// view of the window is marked for layout.
void InvalidateLayoutOfAll(views::View* view) {
  view->InvalidateLayout();
  for (views::View* child : view->children()) {
    InvalidateLayoutOfAll(child);
  }
}

void RelayoutWindowsOf(Profile* profile) {
  for (BrowserWindowInterface* window : GetAllBrowserWindowInterfaces()) {
    if (window->GetProfile() != profile) {
      continue;
    }
    views::Widget* widget = views::Widget::GetWidgetForNativeWindow(
        window->GetWindow()->GetNativeWindow());
    if (widget && widget->GetRootView()) {
      InvalidateLayoutOfAll(widget->GetRootView());
    }
  }
}

// One pref observer per profile, made the first time one of its tabs lays
// out.
class Watcher : public base::SupportsUserData::Data {
 public:
  explicit Watcher(Profile* profile) {
    registrar_.Init(profile->GetPrefs());
    // The profile owns this watcher, so it outlives the registrar.
    registrar_.Add(prefs::kShowTabCloseButtons,
                   base::BindRepeating(&RelayoutWindowsOf,
                                       base::Unretained(profile)));
  }

 private:
  PrefChangeRegistrar registrar_;
};

}  // namespace

bool OganessonShowsTabCloseButtons(const BrowserWindowInterface* window) {
  if (!window) {
    return true;
  }
  // The watcher is user data on the profile; reading the pref doesn't change
  // the profile.
  Profile* profile = const_cast<Profile*>(window->GetProfile());
  if (!profile->GetUserData(kWatcherKey)) {
    profile->SetUserData(kWatcherKey, std::make_unique<Watcher>(profile));
  }
  return profile->GetPrefs()->GetBoolean(prefs::kShowTabCloseButtons);
}
