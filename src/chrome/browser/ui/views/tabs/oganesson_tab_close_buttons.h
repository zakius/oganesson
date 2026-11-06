// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_VIEWS_TABS_OGANESSON_TAB_CLOSE_BUTTONS_H_
#define CHROME_BROWSER_UI_VIEWS_TABS_OGANESSON_TAB_CLOSE_BUTTONS_H_

class BrowserWindowInterface;

// The "Show close buttons on tabs" setting (docs/tab-behavior.md), which
// replaces ungoogled-chromium's hide-tab-close-buttons flag. The horizontal
// and vertical tab strips ask it as they lay out a tab. When the setting
// changes, every window of the profile lays out its tabs again. True for a
// tab with no window yet.
bool OganessonShowsTabCloseButtons(const BrowserWindowInterface* window);

#endif  // CHROME_BROWSER_UI_VIEWS_TABS_OGANESSON_TAB_CLOSE_BUTTONS_H_
