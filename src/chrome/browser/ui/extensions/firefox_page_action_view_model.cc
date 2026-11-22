// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/extensions/firefox_page_action_view_model.h"

#include <memory>
#include <utility>

#include "base/memory/ptr_util.h"
#include "base/memory/scoped_refptr.h"
#include "chrome/browser/extensions/extension_action_dispatcher.h"
#include "chrome/browser/extensions/extension_action_runner.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/extensions/extension_action_delegate.h"
#include "chrome/browser/ui/extensions/extension_action_view_model.h"
#include "components/sessions/content/session_tab_helper.h"
#include "content/public/browser/web_contents.h"
#include "extensions/browser/extension_registry.h"
#include "extensions/common/extension.h"

// static
std::unique_ptr<ExtensionActionViewModel>
ExtensionActionViewModel::CreateForFirefoxPageAction(
    const extensions::Extension& extension,
    extensions::ExtensionAction& action,
    BrowserWindowInterface* browser,
    std::unique_ptr<ExtensionActionDelegate> delegate) {
  // WrapUnique() because the constructor is private.
  return base::WrapUnique(new ExtensionActionViewModel(
      base::WrapRefCounted(&extension), browser, &action,
      extensions::ExtensionRegistry::Get(browser->GetProfile()),
      std::move(delegate)));
}

extensions::ExtensionAction::ShowAction RunFirefoxPageAction(
    extensions::ExtensionActionRunner& runner,
    const extensions::Extension& extension,
    const extensions::ExtensionAction& action,
    content::WebContents& web_contents) {
  runner.GrantTabPermissions({&extension});
  const int tab_id = sessions::SessionTabHelper::IdForTab(&web_contents).id();
  if (!action.GetIsVisible(tab_id)) {
    return extensions::ExtensionAction::ShowAction::kNone;
  }
  if (action.HasPopup(tab_id)) {
    return extensions::ExtensionAction::ShowAction::kShowPopup;
  }
  extensions::ExtensionActionDispatcher::Get(web_contents.GetBrowserContext())
      ->DispatchExtensionActionClicked(action, &web_contents, &extension);
  return extensions::ExtensionAction::ShowAction::kNone;
}
