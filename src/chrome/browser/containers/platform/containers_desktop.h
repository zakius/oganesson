// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINERS_DESKTOP_H_
#define CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINERS_DESKTOP_H_

#include <string>
#include <string_view>
#include <vector>

#include "base/memory/weak_ptr.h"
#include "ui/base/models/image_model.h"
#include "ui/base/window_open_disposition.h"

class BrowserWindowInterface;
class GURL;
struct NavigateParams;
class Profile;

namespace content {
class NavigationHandle;
class WebContents;
class WebUIDataSource;
}  // namespace content

namespace gfx {
class Canvas;
class Rect;
}  // namespace gfx

namespace tabs {
class TabInterface;
}

namespace containers {

struct Container;

// Settings' "Ask every time" for new tabs, a value of the pref
// containers.new_tab: the New Tab button shows the containers menu
// (AskForNewTab()). ContainersService::NewTabContainer() knows no container
// by this id, so Ctrl+T opens a tab outside containers.
inline constexpr char kAskForNewTab[] = "ask";

// The container's icon in its color, `size` pixels square.
ui::ImageModel IconOf(const Container& container, int size = 16);

// The same icon as an image, for views that would recolor a vector icon.
ui::ImageModel IconImageOf(const Container& container, int size = 16);

// Navigate(), with the new tab in container `id`, or outside containers when
// `id` is empty. For a new tab or window: `params` has no contents yet.
// Returns the new tab's navigation.
base::WeakPtr<content::NavigationHandle> NavigateInContainer(
    NavigateParams* params,
    const std::string& id);

// Navigate() for a page the user opens from the active tab of
// `params->browser`, as Alt+Enter in the address bar or a link dropped on the
// tab strip: a new tab or window opens in the active tab's container.
base::WeakPtr<content::NavigationHandle> NavigateFromActiveTab(
    NavigateParams* params);

// Opens `url` in a new tab or window of `browser`, as `disposition` says, in
// container `id`, or outside containers when `id` is empty. `source`, the tab
// it opens from, if any, places the new tab as a link from it would be.
// Returns the new tab's contents.
content::WebContents* OpenInContainer(BrowserWindowInterface* browser,
                                      const GURL& url,
                                      const std::string& id,
                                      WindowOpenDisposition disposition,
                                      content::WebContents* source = nullptr);

// The container that a new tab of `browser` opens in, as Settings says: an
// id, or empty.
std::string NewTabContainer(BrowserWindowInterface* browser);

// Opens the new tab page in container `id` of `browser`.
void NewTabInContainer(BrowserWindowInterface* browser, const std::string& id);

// The commands that open a new tab in the active tab's container or in one
// of the user's first nine containers, for `browser` to enable: none for a
// profile without containers.
std::vector<int> CommandIds(BrowserWindowInterface* browser);

// Runs command `id` of `browser` if it is one of CommandIds(). Returns whether
// it was.
bool ExecuteCommand(BrowserWindowInterface* browser, int id);

// Reopens each tab of `tabs` in container `id` in its place, and closes it.
void ReopenTabsInContainer(const std::vector<tabs::TabInterface*>& tabs,
                           const std::string& id);

// Settings' containers page's strings, and its icons and colors.
void AddSettingsStrings(content::WebUIDataSource* source);

// Opens Settings' containers page.
void ShowContainersSettings(Profile* profile);

// Draws the color line of the container `tab` is in along the bottom of
// `bounds`, as Firefox marks container tabs. Horizontal and vertical tabs
// both draw it.
void PaintTabLine(const tabs::TabInterface* tab,
                  const gfx::Rect& bounds,
                  gfx::Canvas* canvas);

}  // namespace containers

#endif  // CHROME_BROWSER_CONTAINERS_PLATFORM_CONTAINERS_DESKTOP_H_
