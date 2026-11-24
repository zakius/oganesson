// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/views/toolbar/firefox_page_actions_view.h"

#include <memory>
#include <optional>
#include <string>
#include <utility>

#include "base/functional/bind.h"
#include "base/location.h"
#include "base/scoped_observation.h"
#include "base/task/sequenced_task_runner.h"
#include "chrome/browser/extensions/extension_view_host.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/extensions/accelerator_priority.h"
#include "chrome/browser/ui/extensions/extension_action_delegate.h"
#include "chrome/browser/ui/extensions/extension_action_view_model.h"
#include "chrome/browser/ui/extensions/extension_popup_types.h"
#include "chrome/browser/ui/extensions/extensions_container.h"
#include "chrome/browser/ui/layout_constants.h"
#include "chrome/browser/ui/toolbar/toolbar_action_hover_card_types.h"
#include "chrome/browser/ui/views/extensions/extension_popup.h"
#include "chrome/browser/ui/views/toolbar/toolbar_bubble_arrow.h"
#include "components/sessions/content/session_tab_helper.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/web_contents.h"
#include "extensions/browser/extension_action.h"
#include "extensions/browser/extension_action_manager.h"
#include "extensions/browser/extension_host.h"
#include "extensions/browser/extension_host_observer.h"
#include "extensions/browser/extension_util.h"
#include "extensions/common/api/extension_action/action_info.h"
#include "extensions/common/command.h"
#include "extensions/common/extension.h"
#include "extensions/common/extension_id.h"
#include "extensions/common/firefox_add_on.h"
#include "ui/base/accelerators/accelerator.h"
#include "ui/base/dragdrop/drag_drop_types.h"
#include "ui/base/metadata/metadata_impl_macros.h"
#include "ui/views/bubble/bubble_anchor.h"
#include "ui/views/focus/focus_manager.h"
#include "ui/views/layout/box_layout.h"
#include "ui/views/view_observer.h"
#include "ui/views/view_utils.h"

namespace {

// The page action of `extension` that has a button, or null.
extensions::ExtensionAction* PageActionOf(
    Profile* profile,
    const extensions::Extension& extension) {
  extensions::ExtensionActionManager* manager =
      extensions::ExtensionActionManager::Get(profile);
  if (extensions::ExtensionAction* second =
          manager->GetFirefoxPageAction(extension)) {
    return second;
  }
  extensions::ExtensionAction* action = manager->GetExtensionAction(extension);
  if (action && action->action_type() == extensions::ActionInfo::Type::kPage &&
      extensions::IsFirefoxAddOn(extension)) {
    return action;
  }
  return nullptr;
}

// A page action's button. Its class name and ExtensionId find it in UI
// DevTools, apart from the toolbar's buttons.
class FirefoxPageActionView : public ToolbarActionView {
  METADATA_HEADER(FirefoxPageActionView, ToolbarActionView)

 public:
  FirefoxPageActionView(ExtensionActionViewModel* model,
                        ToolbarActionView::Delegate* delegate,
                        const extensions::ExtensionId& extension_id)
      : ToolbarActionView(model, delegate), extension_id_(extension_id) {}

  std::string GetExtensionId() const { return extension_id_; }

 private:
  const extensions::ExtensionId extension_id_;
};

BEGIN_METADATA(FirefoxPageActionView)
ADD_READONLY_PROPERTY_METADATA(std::string, ExtensionId)
END_METADATA

}  // namespace

// The popup and the shortcut of a page action's button, as
// ExtensionActionDelegateDesktop has them for a toolbar button: the popup
// opens anchored to the button, and the shortcut is on the window's focus
// manager. Only a page action next to another action registers its
// shortcut: an add-on's only action has it on its toolbar button already,
// and a focus manager takes one extension target per key.
class FirefoxPageActionsView::ActionDelegate
    : public ExtensionActionDelegate,
      public ui::AcceleratorTarget,
      public extensions::ExtensionHostObserver,
      public views::ViewObserver {
 public:
  ActionDelegate(BrowserWindowInterface* browser, bool registers_command)
      : browser_(browser), registers_command_(registers_command) {}
  ActionDelegate(const ActionDelegate&) = delete;
  ActionDelegate& operator=(const ActionDelegate&) = delete;
  ~ActionDelegate() override = default;

  void SetButton(ToolbarActionView* button) {
    button_ = button;
    button_observation_.Observe(button);
  }

  // ExtensionActionDelegate:
  void AttachToModel(ExtensionActionViewModel* model) override {
    model_ = model;
  }

  void DetachFromModel() override { model_ = nullptr; }

  void RegisterCommand() override {
    views::FocusManager* focus_manager =
        button_ ? button_->GetFocusManager() : nullptr;
    extensions::Command command;
    if (!registers_command_ || keybinding_ || !focus_manager ||
        !model_->GetExtensionCommand(&command)) {
      return;
    }
    keybinding_ = command.accelerator();
    focus_manager->RegisterAccelerator(*keybinding_,
                                       kExtensionAcceleratorPriority, this);
  }

  void UnregisterCommand() override {
    views::FocusManager* focus_manager =
        button_ ? button_->GetFocusManager() : nullptr;
    if (!keybinding_ || !focus_manager) {
      return;
    }
    focus_manager->UnregisterAccelerator(*keybinding_, this);
    keybinding_.reset();
  }

  bool IsShowingPopup() const override { return popup_host_ != nullptr; }

  void HidePopup() override {
    if (!popup_host_) {
      return;
    }
    popup_host_->Close();
    // The host may close later; the button forgets it now.
    if (popup_host_) {
      OnPopupClosed();
    }
  }

  gfx::NativeView GetPopupNativeViewForTesting() override {
    return gfx::NativeView();
  }

  void TriggerPopup(std::unique_ptr<extensions::ExtensionViewHost> host,
                    PopupShowAction show_action,
                    bool by_user,
                    ShowPopupCallback callback) override {
    if (!button_) {
      if (callback) {
        std::move(callback).Run(nullptr);
      }
      return;
    }
    // One popup at a time, the toolbar's included.
    if (ExtensionsContainer* container = ExtensionsContainer::From(*browser_)) {
      container->HideActivePopup();
    }
    HidePopup();
    popup_host_ = host.get();
    popup_host_observation_.Observe(popup_host_.get());
    ExtensionPopup::ShowPopup(
        browser_, std::move(host), views::BubbleAnchor(button_.get()),
        GetToolbarBubbleArrow(button_.get()), show_action, std::move(callback));
    // The button stays pressed while its popup is open. A hidden button has
    // no popup to press for (ToolbarActionView::OnPopupShown()).
    if (button_->GetVisible()) {
      button_->OnPopupShown(by_user);
    }
  }

  void ShowContextMenuAsFallback() override {
    if (button_) {
      button_->ShowContextMenuAsFallback();
    }
  }

  void CloseExtensionsMenuIfOpen() override {
    if (ExtensionsContainer* container = ExtensionsContainer::From(*browser_)) {
      container->CloseExtensionsMenuIfOpen();
    }
  }

  // ui::AcceleratorTarget:
  bool AcceleratorPressed(const ui::Accelerator& accelerator) override {
    return model_->TryHandleAcceleratorPress();
  }

  bool CanHandleAccelerators() const override {
    return model_->CanHandleAccelerators();
  }

  // extensions::ExtensionHostObserver:
  void OnExtensionHostDestroyed(extensions::ExtensionHost* host) override {
    OnPopupClosed();
  }

  // views::ViewObserver:
  void OnViewIsDeleting(views::View* observed_view) override {
    button_observation_.Reset();
    button_ = nullptr;
  }

 private:
  void OnPopupClosed() {
    popup_host_observation_.Reset();
    popup_host_ = nullptr;
    if (button_) {
      button_->OnPopupClosed();
    }
  }

  const raw_ptr<BrowserWindowInterface> browser_;
  const bool registers_command_;
  raw_ptr<ExtensionActionViewModel> model_ = nullptr;
  raw_ptr<ToolbarActionView> button_ = nullptr;
  raw_ptr<extensions::ExtensionViewHost> popup_host_ = nullptr;
  std::optional<ui::Accelerator> keybinding_;
  base::ScopedObservation<extensions::ExtensionHost,
                          extensions::ExtensionHostObserver>
      popup_host_observation_{this};
  base::ScopedObservation<views::View, views::ViewObserver> button_observation_{
      this};
};

FirefoxPageActionsView::FirefoxPageActionsView(BrowserWindowInterface* browser)
    : browser_(browser),
      profile_(browser->GetProfile()),
      buttons_user_data_(browser->GetUnownedUserDataHost(), *this) {
  SetLayoutManager(std::make_unique<views::BoxLayout>());
  dispatcher_observation_.Observe(
      extensions::ExtensionActionDispatcher::Get(profile_));
  registry_observation_.Observe(extensions::ExtensionRegistry::Get(profile_));
  active_tab_subscription_ =
      browser_->RegisterActiveTabDidChange(base::BindRepeating(
          [](FirefoxPageActionsView* view, BrowserWindowInterface* browser) {
            view->Update();
          },
          base::Unretained(this)));
  Rebuild();
}

FirefoxPageActionsView::~FirefoxPageActionsView() {
  RemoveAllChildViews();
}

bool FirefoxPageActionsView::RunPageAction(
    const extensions::Extension& extension) {
  for (const std::unique_ptr<ExtensionActionViewModel>& model : models_) {
    if (model->GetId() == extension.id()) {
      model->ExecuteUserAction(
          ToolbarActionViewModel::InvocationSource::kCommand);
      return true;
    }
  }
  return false;
}

content::WebContents* FirefoxPageActionsView::GetCurrentWebContents() {
  tabs::TabInterface* tab = browser_->GetActiveTabInterface();
  return tab ? tab->GetContents() : nullptr;
}

views::LabelButton* FirefoxPageActionsView::GetOverflowReferenceView() const {
  return nullptr;
}

gfx::Size FirefoxPageActionsView::GetToolbarActionSize() {
  // As high as the location bar's other decorations.
  const int size =
      GetLayoutConstant(LayoutConstant::kLocationBarHeight) -
      2 * GetLayoutConstant(LayoutConstant::kLocationBarElementPadding);
  return gfx::Size(size, size);
}

void FirefoxPageActionsView::MovePinnedActionBy(const std::string& action_id,
                                                int move_by) {}

void FirefoxPageActionsView::UpdateHoverCard(
    ToolbarActionView* action_view,
    ToolbarActionHoverCardUpdateType update_type) {}

void FirefoxPageActionsView::OnContextMenuShown(const std::string& action_id) {}

void FirefoxPageActionsView::OnContextMenuClosed(const std::string& action_id) {
}

bool FirefoxPageActionsView::IsFocusOnExtensionAction() const {
  return false;
}

void FirefoxPageActionsView::WriteDragDataForView(views::View* sender,
                                                  const gfx::Point& press_pt,
                                                  ui::OSExchangeData* data) {}

int FirefoxPageActionsView::GetDragOperationsForView(views::View* sender,
                                                     const gfx::Point& p) {
  return ui::DragDropTypes::DRAG_NONE;
}

bool FirefoxPageActionsView::CanStartDragForView(views::View* sender,
                                                 const gfx::Point& press_pt,
                                                 const gfx::Point& p) {
  return false;
}

void FirefoxPageActionsView::Rebuild() {
  RemoveAllChildViews();
  models_.clear();
  extensions::ExtensionActionManager* manager =
      extensions::ExtensionActionManager::Get(profile_);
  for (const auto& extension :
       extensions::ExtensionRegistry::Get(profile_)->enabled_extensions()) {
    extensions::ExtensionAction* action = PageActionOf(profile_, *extension);
    if (!action ||
        (profile_->IsOffTheRecord() &&
         !extensions::util::IsIncognitoEnabled(extension->id(), profile_))) {
      continue;
    }
    const bool is_second_action =
        action != manager->GetExtensionAction(*extension);
    auto delegate =
        std::make_unique<ActionDelegate>(browser_, is_second_action);
    ActionDelegate* const delegate_ptr = delegate.get();
    models_.push_back(ExtensionActionViewModel::CreateForFirefoxPageAction(
        *extension, *action, browser_, std::move(delegate)));
    auto button = std::make_unique<FirefoxPageActionView>(
        models_.back().get(), this, extension->id());
    // Before the button is in the window, where it registers its shortcut.
    delegate_ptr->SetButton(button.get());
    AddChildView(std::move(button));
  }
  Update();
}

void FirefoxPageActionsView::Update() {
  update_scheduled_ = false;
  content::WebContents* contents = GetCurrentWebContents();
  const int tab_id = sessions::SessionTabHelper::IdForTab(contents).id();
  const extensions::ExtensionSet& extensions =
      extensions::ExtensionRegistry::Get(profile_)->enabled_extensions();
  bool any_shown = false;
  for (views::View* child : children()) {
    auto* button = views::AsViewClass<FirefoxPageActionView>(child);
    const extensions::Extension* extension =
        extensions.GetByID(button->GetExtensionId());
    extensions::ExtensionAction* action =
        extension ? PageActionOf(profile_, *extension) : nullptr;
    const bool shown = contents && action && action->GetIsVisible(tab_id);
    button->SetVisible(shown);
    if (!shown) {
      continue;
    }
    any_shown = true;
    button->UpdateState();
    // Firefox's tooltip is the title alone, without the site access that
    // the toolbar's hover card shows.
    std::u16string title = button->view_model()->GetActionTitle(contents);
    if (title.empty()) {
      title = button->view_model()->GetActionName();
    }
    button->SetTooltipText(title);
  }
  SetVisible(any_shown);
  PreferredSizeChanged();
}

void FirefoxPageActionsView::ScheduleUpdate() {
  if (update_scheduled_) {
    return;
  }
  update_scheduled_ = true;
  base::SequencedTaskRunner::GetCurrentDefault()->PostTask(
      FROM_HERE, base::BindOnce(&FirefoxPageActionsView::Update,
                                weak_factory_.GetWeakPtr()));
}

void FirefoxPageActionsView::OnExtensionActionUpdated(
    extensions::ExtensionAction* extension_action,
    content::WebContents* web_contents,
    content::BrowserContext* browser_context) {
  if (web_contents && web_contents != GetCurrentWebContents()) {
    return;
  }
  // Later: on a navigation, ExtensionActionDispatcher::ClearAllValuesForTab()
  // clears a page action next to another action after it notifies the
  // other one.
  ScheduleUpdate();
}

void FirefoxPageActionsView::OnShuttingDown() {
  dispatcher_observation_.Reset();
}

void FirefoxPageActionsView::OnExtensionLoaded(
    content::BrowserContext* browser_context,
    const extensions::Extension* extension) {
  if (PageActionOf(profile_, *extension)) {
    Rebuild();
  }
}

void FirefoxPageActionsView::OnExtensionUnloaded(
    content::BrowserContext* browser_context,
    const extensions::Extension* extension,
    extensions::UnloadedExtensionReason reason) {
  for (views::View* child : children()) {
    if (views::AsViewClass<FirefoxPageActionView>(child)->GetExtensionId() ==
        extension->id()) {
      Rebuild();
      return;
    }
  }
}

void FirefoxPageActionsView::OnShutdown(
    extensions::ExtensionRegistry* registry) {
  registry_observation_.Reset();
}

BEGIN_METADATA(FirefoxPageActionsView)
END_METADATA
