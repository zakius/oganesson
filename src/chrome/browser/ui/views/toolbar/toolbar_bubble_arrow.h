// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_VIEWS_TOOLBAR_TOOLBAR_BUBBLE_ARROW_H_
#define CHROME_BROWSER_UI_VIEWS_TOOLBAR_TOOLBAR_BUBBLE_ARROW_H_

#include "ui/views/bubble/bubble_border.h"

namespace views {
class View;
}

// The arrow for a bubble anchored to a toolbar button: TOP_RIGHT, or TOP_LEFT
// for a button in the leading half of its window, such as a pinned extension
// action or a page action placed there. Linux doesn't move bubbles back on
// screen (PlatformStyle::kAdjustBubbleIfOffscreen), so a TOP_RIGHT bubble
// there would open past the window's leading edge. Defined in
// toolbar_view_items.cc.
views::BubbleBorder::Arrow GetToolbarBubbleArrow(const views::View* anchor);

#endif  // CHROME_BROWSER_UI_VIEWS_TOOLBAR_TOOLBAR_BUBBLE_ARROW_H_
