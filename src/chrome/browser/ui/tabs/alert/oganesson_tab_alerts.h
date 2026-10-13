// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_TABS_ALERT_OGANESSON_TAB_ALERTS_H_
#define CHROME_BROWSER_UI_TABS_ALERT_OGANESSON_TAB_ALERTS_H_

#include "base/callback_list.h"
#include "base/functional/callback.h"
#include "components/tabs/public/tab_alert.h"

namespace tabs {

class TabInterface;

// The "Show sound icon on tabs" setting (docs/tab-behavior.md). With it off,
// TabAlertController never activates kAudioPlaying, so the tab strip,
// vertical tabs, hover cards and tab search all lose the sound icon. The
// muted icon and every other alert stay.
bool OganessonShowsAlert(const TabInterface& tab, TabAlert alert);

// Runs `callback` with the tab's recently-audible state each time the
// setting changes, so open tabs follow it.
base::CallbackListSubscription OganessonOnAudioIndicatorChanged(
    TabInterface& tab,
    base::RepeatingCallback<void(bool)> callback);

}  // namespace tabs

#endif  // CHROME_BROWSER_UI_TABS_ALERT_OGANESSON_TAB_ALERTS_H_
