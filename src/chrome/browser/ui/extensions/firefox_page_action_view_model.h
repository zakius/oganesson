// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_EXTENSIONS_FIREFOX_PAGE_ACTION_VIEW_MODEL_H_
#define CHROME_BROWSER_UI_EXTENSIONS_FIREFOX_PAGE_ACTION_VIEW_MODEL_H_

#include "extensions/browser/extension_action.h"

namespace content {
class WebContents;
}

namespace extensions {
class Extension;
class ExtensionActionRunner;
}  // namespace extensions

// Firefox add-ons (dubna's webextensions/README.md): a click on the location
// bar button of `action`, the page action next to `extension`'s other action
// (extensions/common/firefox_page_action.h), in `web_contents`. It runs as
// ExtensionActionRunner::RunAction() runs an add-on's one action, which it
// looks up itself: the add-on gets activeTab, then the page action's popup
// opens (kShowPopup) or pageAction.onClicked fires. A hidden page action does
// nothing.
extensions::ExtensionAction::ShowAction RunFirefoxPageAction(
    extensions::ExtensionActionRunner& runner,
    const extensions::Extension& extension,
    const extensions::ExtensionAction& action,
    content::WebContents& web_contents);

#endif  // CHROME_BROWSER_UI_EXTENSIONS_FIREFOX_PAGE_ACTION_VIEW_MODEL_H_
