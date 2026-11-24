// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_VIEWS_TOOLBAR_FIREFOX_PAGE_ACTIONS_VIEW_H_
#define CHROME_BROWSER_UI_VIEWS_TOOLBAR_FIREFOX_PAGE_ACTIONS_VIEW_H_

#include <memory>
#include <string>
#include <vector>

#include "base/callback_list.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/scoped_observation.h"
#include "chrome/browser/extensions/extension_action_dispatcher.h"
#include "chrome/browser/extensions/firefox_page_action_buttons.h"
#include "chrome/browser/ui/views/toolbar/toolbar_action_view.h"
#include "extensions/browser/extension_registry.h"
#include "extensions/browser/extension_registry_observer.h"
#include "ui/base/metadata/metadata_header_macros.h"
#include "ui/base/unowned_user_data/scoped_unowned_user_data.h"
#include "ui/views/view.h"

class BrowserWindowInterface;
class ExtensionActionViewModel;
class Profile;

// Firefox add-ons (dubna's webextensions/README.md): the buttons of their page
// actions in the location bar, as Firefox has them. A button shows on the
// tabs where its page action is shown, with the action's icon, badge and
// title; a click, or the add-on's _execute_page_action shortcut, opens the
// action's popup anchored to it or fires pageAction.onClicked. Each button is
// Chromium's toolbar button of an extension action (ToolbarActionView) on a
// model of the page action, with its context menu. A page action is the one
// next to an add-on's other action (extensions/common/firefox_page_action.h),
// or the only action of a Manifest V2 Firefox add-on, which keeps its toolbar
// button and the shortcut there too. The toolbar makes this view, and the
// location bar lays it out left of Chromium's page actions. It is the
// window's FirefoxPageActionButtons, for pageAction.openPopup() and the menus
// command _execute_page_action.
class FirefoxPageActionsView
    : public views::View,
      public extensions::FirefoxPageActionButtons,
      public ToolbarActionView::Delegate,
      public extensions::ExtensionActionDispatcher::Observer,
      public extensions::ExtensionRegistryObserver {
  METADATA_HEADER(FirefoxPageActionsView, views::View)

 public:
  explicit FirefoxPageActionsView(BrowserWindowInterface* browser);
  FirefoxPageActionsView(const FirefoxPageActionsView&) = delete;
  FirefoxPageActionsView& operator=(const FirefoxPageActionsView&) = delete;
  ~FirefoxPageActionsView() override;

  // extensions::FirefoxPageActionButtons:
  bool RunPageAction(const extensions::Extension& extension) override;

  // ToolbarActionView::Delegate:
  content::WebContents* GetCurrentWebContents() override;
  views::LabelButton* GetOverflowReferenceView() const override;
  gfx::Size GetToolbarActionSize() override;
  void MovePinnedActionBy(const std::string& action_id, int move_by) override;
  void UpdateHoverCard(ToolbarActionView* action_view,
                       ToolbarActionHoverCardUpdateType update_type) override;
  void OnContextMenuShown(const std::string& action_id) override;
  void OnContextMenuClosed(const std::string& action_id) override;
  bool IsFocusOnExtensionAction() const override;

  // views::DragController:
  void WriteDragDataForView(views::View* sender,
                            const gfx::Point& press_pt,
                            ui::OSExchangeData* data) override;
  int GetDragOperationsForView(views::View* sender,
                               const gfx::Point& p) override;
  bool CanStartDragForView(views::View* sender,
                           const gfx::Point& press_pt,
                           const gfx::Point& p) override;

 private:
  class ActionDelegate;

  // Makes a button for each add-on with a page action.
  void Rebuild();
  // Shows the buttons of the page actions shown in the active tab.
  void Update();
  void ScheduleUpdate();

  // extensions::ExtensionActionDispatcher::Observer:
  void OnExtensionActionUpdated(
      extensions::ExtensionAction* extension_action,
      content::WebContents* web_contents,
      content::BrowserContext* browser_context) override;
  void OnShuttingDown() override;

  // extensions::ExtensionRegistryObserver:
  void OnExtensionLoaded(content::BrowserContext* browser_context,
                         const extensions::Extension* extension) override;
  void OnExtensionUnloaded(content::BrowserContext* browser_context,
                           const extensions::Extension* extension,
                           extensions::UnloadedExtensionReason reason) override;
  void OnShutdown(extensions::ExtensionRegistry* registry) override;

  const raw_ptr<BrowserWindowInterface> browser_;
  const raw_ptr<Profile> profile_;

  // The models of the buttons, which use them: the buttons go first.
  std::vector<std::unique_ptr<ExtensionActionViewModel>> models_;

  bool update_scheduled_ = false;

  ui::ScopedUnownedUserData<extensions::FirefoxPageActionButtons>
      buttons_user_data_;

  base::CallbackListSubscription active_tab_subscription_;
  base::ScopedObservation<extensions::ExtensionActionDispatcher,
                          extensions::ExtensionActionDispatcher::Observer>
      dispatcher_observation_{this};
  base::ScopedObservation<extensions::ExtensionRegistry,
                          extensions::ExtensionRegistryObserver>
      registry_observation_{this};
  base::WeakPtrFactory<FirefoxPageActionsView> weak_factory_{this};
};

#endif  // CHROME_BROWSER_UI_VIEWS_TOOLBAR_FIREFOX_PAGE_ACTIONS_VIEW_H_
