// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// ToolbarView's items: every toolbar item is a direct child, ordered per
// prefs::kToolbarItems, and any of them moves anywhere by drag and drop.

#include <algorithm>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "base/functional/bind.h"
#include "base/functional/callback_helpers.h"
#include "base/no_destructor.h"
#include "base/pickle.h"
#include "base/strings/strcat.h"
#include "base/values.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/color/chrome_color_id.h"
#include "chrome/browser/ui/layout_constants.h"
#include "chrome/browser/ui/toolbar/app_menu_model.h"
#include "chrome/browser/ui/toolbar/pinned_toolbar/pinned_toolbar_actions_model.h"
#include "chrome/browser/ui/toolbar/toolbar_actions_model.h"
#include "chrome/browser/ui/ui_features.h"
#include "chrome/browser/ui/views/extensions/browser_action_drag_data.h"
#include "chrome/browser/ui/views/extensions/extensions_toolbar_desktop.h"
#include "chrome/browser/ui/views/extensions/extensions_toolbar_button.h"
#include "chrome/browser/ui/views/global_media_controls/media_toolbar_button_view.h"
#include "chrome/browser/ui/views/location_bar/location_bar_view.h"
#include "chrome/browser/ui/views/profiles/avatar_toolbar_button.h"
#include "chrome/browser/ui/views/toolbar/app_menu.h"
#include "chrome/browser/ui/views/toolbar/browser_app_menu_button.h"
#include "chrome/browser/ui/views/toolbar/home_button.h"
#include "chrome/browser/ui/views/toolbar/pinned_action_toolbar_button.h"
#include "chrome/browser/ui/views/toolbar/pinned_toolbar_actions_container.h"
#include "chrome/browser/ui/views/toolbar/reload_button.h"
#include "chrome/browser/ui/views/toolbar/toolbar_action_view.h"
#include "chrome/browser/ui/views/toolbar/toolbar_button.h"
#include "chrome/browser/ui/views/toolbar/toolbar_view.h"
#include "chrome/common/pref_names.h"
#include "components/prefs/pref_service.h"
#include "components/prefs/scoped_user_pref_update.h"
#include "extensions/browser/extension_prefs.h"
#include "ui/actions/actions.h"
#include "ui/base/class_property.h"
#include "ui/base/clipboard/clipboard_format_type.h"
#include "ui/base/dragdrop/drag_drop_types.h"
#include "ui/base/dragdrop/drop_target_event.h"
#include "ui/base/dragdrop/mojom/drag_drop_types.mojom.h"
#include "ui/base/dragdrop/os_exchange_data.h"
#include "ui/color/color_provider.h"
#include "ui/compositor/layer_tree_owner.h"
#include "ui/gfx/canvas.h"
#include "ui/gfx/geometry/rect.h"
#include "ui/views/context_menu_controller.h"
#include "ui/views/controls/button/button_controller.h"

namespace {

// prefs::kToolbarItems token prefixes of pinned extension actions and Chrome's
// pinned buttons.
constexpr std::string_view kExtensionItemPrefix = "extension:";
constexpr std::string_view kActionItemPrefix = "action:";

// The built-in items Customize toolbar can hide, by prefs::kToolbarItems
// token (customize_toolbar_oganesson.cc lists them).
constexpr std::string_view kHideableItems[] = {
    "back", "reload", "location_bar", "extensions", "avatar", "app_menu"};

// Set on an item while ApplyHiddenItems() keeps it hidden.
DEFINE_UI_CLASS_PROPERTY_KEY(bool, kHiddenByPrefKey, false)

bool IsItemHidden(const PrefService* prefs, std::string_view token) {
  return std::ranges::contains(prefs->GetList(prefs::kToolbarHiddenItems),
                               base::Value(token));
}

// With the app menu button hidden, a right click on the toolbar opens the
// app menu where the click was.
class AppMenuFallback : public views::ContextMenuController {
 public:
  explicit AppMenuFallback(ToolbarView* toolbar) : toolbar_(toolbar) {}

 private:
  // views::ContextMenuController:
  void ShowContextMenuForViewImpl(
      views::View* source,
      const gfx::Point& point,
      ui::mojom::MenuSourceType source_type) override {
    BrowserWindowInterface* const browser = toolbar_->browser();
    if (!IsItemHidden(browser->GetProfile()->GetPrefs(), "app_menu")) {
      return;
    }
    menu_.reset();
    model_ = std::make_unique<AppMenuModel>(
        toolbar_, browser, toolbar_->app_menu_icon_controller());
    model_->Init();
    menu_ = std::make_unique<AppMenu>(browser, model_.get(), /*run_types=*/0,
                                      base::DoNothing());
    menu_->RunMenu(toolbar_->GetWidget(), gfx::Rect(point, gfx::Size()),
                   source_type);
  }

  raw_ptr<ToolbarView> toolbar_;
  std::unique_ptr<AppMenuModel> model_;
  std::unique_ptr<AppMenu> menu_;
};

// Drag data of a built-in toolbar item: its pickled token.
const ui::ClipboardFormatType& GetToolbarItemFormatType() {
  static const base::NoDestructor<ui::ClipboardFormatType> format(
      ui::ClipboardFormatType::CustomPlatformType(
          "chromium/x-oganesson-toolbar-item"));
  return *format;
}

}  // namespace

void ToolbarView::InitToolbarItems() {
  const auto apply = base::BindRepeating(&ToolbarView::ApplyToolbarItems,
                                         base::Unretained(this));
  const auto move_by =
      base::BindRepeating(&ToolbarView::MoveItemBy, base::Unretained(this));
  toolbar_items_registrar_.Init(browser_->GetProfile()->GetPrefs());
  toolbar_items_registrar_.Add(prefs::kToolbarItems, apply);
  toolbar_items_registrar_.Add(
      prefs::kToolbarHiddenItems,
      base::BindRepeating(&ToolbarView::ApplyHiddenItems,
                          base::Unretained(this)));
  app_menu_fallback_ = std::make_unique<AppMenuFallback>(this);
  set_context_menu_controller(app_menu_fallback_.get());
  if (extensions_container_) {
    extensions_container_->SetIconsChangedCallback(apply);
    extensions_container_->SetMoveDetachedCallback(move_by);
  }
  if (pinned_toolbar_actions_container_) {
    pinned_toolbar_actions_container_->SetButtonsChangedCallback(apply);
    pinned_toolbar_actions_container_->SetMoveDetachedCallback(move_by);
  }
  // Built-in items drag like pinned ones, and act on release so a press can
  // start a drag. The extensions button drags its container. The location bar stays put; the others move around it.
  // Incognito windows don't change the layout.
  if (!browser_->GetProfile()->IsOffTheRecord()) {
    for (const auto& [token, item] : GetBuiltInItems()) {
      views::View* handle = item;
      if (item && item == extensions_container_.get()) {
        handle = extensions_container_->GetExtensionsButton();
      }
      if (handle && token != "location_bar") {
        handle->set_drag_controller(this);
        static_cast<ToolbarButton*>(handle)
            ->button_controller()
            ->set_notify_action(
                views::ButtonController::NotifyAction::kOnRelease);
      }
    }
  }
  ApplyToolbarItems();
}

void ToolbarView::ShutdownToolbarItems() {
  set_context_menu_controller(nullptr);
  // Hand the pinned items back to their containers, which own their state, so
  // they are destroyed with them.
  if (extensions_container_) {
    extensions_container_->SetIconsChangedCallback({});
    extensions_container_->SetMoveDetachedCallback({});
  }
  if (pinned_toolbar_actions_container_) {
    pinned_toolbar_actions_container_->SetButtonsChangedCallback({});
    pinned_toolbar_actions_container_->SetMoveDetachedCallback({});
  }
  for (views::View* child : View::Views(children())) {
    if (auto* action = views::AsViewClass<ToolbarActionView>(child);
        action && extensions_container_) {
      extensions_container_->ReturnIcon(RemoveChildViewT(action));
    } else if (auto* button = views::AsViewClass<PinnedActionToolbarButton>(child);
               button && pinned_toolbar_actions_container_) {
      pinned_toolbar_actions_container_->AddChildView(RemoveChildViewT(button));
    }
  }
}

std::vector<std::pair<std::string_view, views::View*>>
ToolbarView::GetBuiltInItems() {
  return {{"back", back_.get()},
          {"forward", forward_.get()},
          {"reload", reload_.get()},
          {"home", home_.get()},
          {"split_tabs", split_tabs_.get()},
          {"location_bar", location_bar_view_.get()},
          {"extensions", extensions_container_.get()},
          {"media", media_button_ && !features::IsWebUIMediaButtonEnabled()
                        ? static_cast<MediaToolbarButtonView*>(
                              media_button_.get())
                        : nullptr},
          {"avatar", avatar_.get()},
          {"app_menu", app_menu_button_.get()}};
}

std::string ToolbarView::GetItemToken(views::View* child) {
  for (const auto& [token, item] : GetBuiltInItems()) {
    if (item && item == child) {
      return std::string(token);
    }
  }
  if (auto* action = views::AsViewClass<ToolbarActionView>(child)) {
    return base::StrCat({kExtensionItemPrefix, action->view_model()->GetId()});
  }
  if (auto* button = views::AsViewClass<PinnedActionToolbarButton>(child)) {
    if (const std::optional<std::string> id =
            actions::ActionIdMap::ActionIdToString(button->GetActionId())) {
      return base::StrCat({kActionItemPrefix, *id});
    }
  }
  return {};
}

void ToolbarView::ApplyToolbarItems() {
  if (display_mode_ != DisplayMode::kNormal) {
    return;
  }
  Profile* const profile = browser_->GetProfile();

  // Pinned extension icons come onto the toolbar, new ones just before the
  // extensions button; unpinned ones go back into its container.
  if (extensions_container_) {
    const bool can_show =
        ToolbarActionsModel::CanShowActionsInToolbar(*browser_);
    const auto& pinned =
        extensions_container_->GetToolbarViewModel()->GetPinnedActionIds();
    for (views::View* child : View::Views(children())) {
      auto* action = views::AsViewClass<ToolbarActionView>(child);
      if (action &&
          (!can_show ||
           !std::ranges::contains(pinned, action->view_model()->GetId()))) {
        extensions_container_->ReturnIcon(RemoveChildViewT(action));
      }
    }
    for (const std::string& id : pinned) {
      if (can_show && extensions_container_->GetViewForId(id) &&
          !extensions_container_->IsIconDetached(id)) {
        AddChildViewAt(extensions_container_->TakeIcon(id),
                       GetIndexOf(extensions_container_).value());
      }
    }
  }
  // Likewise Chrome's pinned buttons, new ones where their container is. The
  // container takes back the ones it unpins.
  if (pinned_toolbar_actions_container_) {
    for (actions::ActionId id :
         pinned_toolbar_actions_container_->PinnedActionIds()) {
      PinnedActionToolbarButton* const button =
          pinned_toolbar_actions_container_->GetPinnedButton(id);
      if (button && button->parent() == pinned_toolbar_actions_container_) {
        AddChildViewAt(pinned_toolbar_actions_container_->TakeButton(id),
                       GetIndexOf(pinned_toolbar_actions_container_).value());
      }
    }
  }

  // Drop the tokens of uninstalled extensions and unpinned buttons. A
  // disabled extension stays pinned, and keeps its place.
  const base::ListValue& items = profile->GetPrefs()->GetList(prefs::kToolbarItems);
  if (!profile->IsOffTheRecord()) {
    const extensions::ExtensionIdList pinned_extensions =
        extensions::ExtensionPrefs::Get(profile)->GetPinnedExtensions();
    const auto is_stale = [&](const base::Value& item) {
      const std::string* token = item.GetIfString();
      if (!token) {
        return true;
      }
      if (token->starts_with(kExtensionItemPrefix)) {
        return !std::ranges::contains(
            pinned_extensions, token->substr(kExtensionItemPrefix.size()));
      }
      if (token->starts_with(kActionItemPrefix)) {
        const std::optional<actions::ActionId> id =
            actions::ActionIdMap::StringToActionId(
                token->substr(kActionItemPrefix.size()));
        return !id || !PinnedToolbarActionsModel::Get(profile)->Contains(*id);
      }
      return false;
    };
    if (std::ranges::any_of(items, is_stale)) {
      // Re-enters this function through the pref observer.
      ScopedListPrefUpdate(profile->GetPrefs(), prefs::kToolbarItems)
          ->EraseIf(is_stale);
      return;
    }
  }

  std::vector<views::View*> listed;
  for (const base::Value& item : items) {
    for (views::View* child : children()) {
      if (item.is_string() && GetItemToken(child) == item.GetString() &&
          !std::ranges::contains(listed, child)) {
        listed.push_back(child);
      }
    }
  }
  const bool reset = items.empty();
  if (reset) {
    for (const auto& [token, item] : GetBuiltInItems()) {
      if (item && item->parent() == this) {
        listed.push_back(item);
      }
    }
  }
  View::Views order = children();
  auto next = listed.begin();
  for (auto& child : order) {
    if (std::ranges::contains(listed, child.get())) {
      child = *next++;
    }
  }
  for (size_t i = 0; i < order.size(); ++i) {
    ReorderChildView(order[i], i);
  }
  if (reset) {
    // The default order, also right after Customize toolbar's reset clears
    // the list (#62): the built-in items in the order they were made, then
    // pinned extension icons just before the extensions button and Chrome's
    // pinned buttons where their container is.
    const auto move_before = [this](views::View* item, views::View* anchor) {
      const size_t from = GetIndexOf(item).value();
      const size_t to = GetIndexOf(anchor).value();
      ReorderChildView(item, from < to ? to - 1 : to);
    };
    if (extensions_container_) {
      for (const std::string& id :
           extensions_container_->GetToolbarViewModel()->GetPinnedActionIds()) {
        for (views::View* child : children()) {
          auto* action = views::AsViewClass<ToolbarActionView>(child);
          if (action && action->view_model()->GetId() == id) {
            move_before(action, extensions_container_.get());
            break;
          }
        }
      }
    }
    if (pinned_toolbar_actions_container_) {
      for (actions::ActionId id :
           pinned_toolbar_actions_container_->PinnedActionIds()) {
        PinnedActionToolbarButton* const button =
            pinned_toolbar_actions_container_->GetPinnedButton(id);
        if (button && button->parent() == this) {
          move_before(button, pinned_toolbar_actions_container_.get());
        }
      }
    }
  }
  ApplyHiddenItems();
  InvalidateLayout();
}

void ToolbarView::ApplyHiddenItems() {
  if (display_mode_ != DisplayMode::kNormal) {
    return;
  }
  const PrefService* const prefs = browser_->GetProfile()->GetPrefs();
  for (const auto& [token, item] : GetBuiltInItems()) {
    if (!item || !std::ranges::contains(kHideableItems, token)) {
      continue;
    }
    if (IsItemHidden(prefs, token)) {
      item->SetProperty(kHiddenByPrefKey, true);
      item->SetVisible(false);
    } else if (item->GetProperty(kHiddenByPrefKey)) {
      item->ClearProperty(kHiddenByPrefKey);
      item->SetVisible(true);
    }
  }
}

void ToolbarView::ReapplyHiddenItem(views::View* child) {
  if (child->GetVisible() && child->GetProperty(kHiddenByPrefKey)) {
    child->SetVisible(false);
  }
}

base::ListValue ToolbarView::WithAbsentItems(std::vector<std::string> tokens) {
  std::string previous;
  for (const base::Value& item :
       browser_->GetProfile()->GetPrefs()->GetList(prefs::kToolbarItems)) {
    if (!item.is_string()) {
      continue;
    }
    const std::string& token = item.GetString();
    if (!std::ranges::contains(tokens, token)) {
      tokens.insert(previous.empty()
                        ? tokens.begin()
                        : std::next(std::ranges::find(tokens, previous)),
                    token);
    }
    previous = token;
  }
  base::ListValue list;
  for (std::string& token : tokens) {
    list.Append(std::move(token));
  }
  return list;
}

void ToolbarView::MoveItemBy(views::View* item, int delta) {
  if (browser_->GetProfile()->IsOffTheRecord()) {
    return;
  }
  std::vector<std::string> tokens;
  std::vector<views::View*> views;
  for (views::View* child : children()) {
    std::string token = GetItemToken(child);
    if (!token.empty()) {
      tokens.push_back(std::move(token));
      views.push_back(child);
    }
  }
  const auto it = std::ranges::find(views, item);
  if (it == views.end()) {
    return;
  }
  const int from = it - views.begin();
  for (int to = from + delta; to >= 0 && to < static_cast<int>(views.size());
       to += delta) {
    if (views[to]->GetVisible()) {
      std::string token = std::move(tokens[from]);
      tokens.erase(tokens.begin() + from);
      tokens.insert(tokens.begin() + to, std::move(token));
      browser_->GetProfile()->GetPrefs()->SetList(
          prefs::kToolbarItems, WithAbsentItems(std::move(tokens)));
      return;
    }
  }
}

size_t ToolbarView::GetItemDropIndex(int x) const {
  const int mirrored_x = GetMirroredXInView(x);
  for (size_t i = 0; i < children().size(); ++i) {
    const views::View* child = children()[i];
    if (child->GetVisible() && mirrored_x < child->bounds().CenterPoint().x()) {
      return i;
    }
  }
  return children().size();
}

std::string ToolbarView::GetDraggedToken(const ui::OSExchangeData& data) {
  if (display_mode_ != DisplayMode::kNormal ||
      browser_->GetProfile()->IsOffTheRecord()) {
    return {};
  }
  std::string token;
  if (data.HasCustomFormat(GetToolbarItemFormatType())) {
    std::optional<base::Pickle> pickle =
        data.GetPickledData(GetToolbarItemFormatType());
    if (!pickle || !base::PickleIterator(*pickle).ReadString(&token)) {
      return {};
    }
  } else {
    // A pinned extension action or Chrome button, dragged by its container.
    BrowserActionDragData action;
    if (!action.Read(data) || !action.IsFromProfile(browser_->GetProfile())) {
      return {};
    }
    const bool is_action =
        actions::ActionIdMap::StringToActionId(action.id()).has_value();
    token = base::StrCat(
        {is_action ? kActionItemPrefix : kExtensionItemPrefix, action.id()});
  }
  for (views::View* child : children()) {
    if (GetItemToken(child) == token) {
      return token;
    }
  }
  return {};
}

bool ToolbarView::GetDropFormats(
    int* formats,
    std::set<ui::ClipboardFormatType>* format_types) {
  format_types->insert(GetToolbarItemFormatType());
  return BrowserActionDragData::GetDropFormats(format_types);
}

bool ToolbarView::AreDropTypesRequired() {
  return true;
}

bool ToolbarView::CanDrop(const ui::OSExchangeData& data) {
  return !GetDraggedToken(data).empty();
}

int ToolbarView::OnDragUpdated(const ui::DropTargetEvent& event) {
  if (GetDraggedToken(event.data()).empty()) {
    return ui::DragDropTypes::DRAG_NONE;
  }
  const size_t index = GetItemDropIndex(event.x());
  int x = index < children().size() ? children()[index]->bounds().x()
                                    : GetContentsBounds().right();
  // Center the indicator in the gap before an item, not on its edge.
  if (index > 0) {
    x -= GetLayoutConstant(LayoutConstant::kToolbarIconDefaultMargin);
  }
  if (drop_x_ != x) {
    drop_x_ = x;
    SchedulePaint();
  }
  return ui::DragDropTypes::DRAG_MOVE;
}

void ToolbarView::OnDragExited() {
  drop_x_.reset();
  SchedulePaint();
}

views::View::DropCallback ToolbarView::GetDropCallback(
    const ui::DropTargetEvent& event) {
  OnDragExited();
  const std::string dragged = GetDraggedToken(event.data());
  if (dragged.empty()) {
    return base::NullCallback();
  }
  const size_t drop_index = GetItemDropIndex(event.x());
  std::vector<std::string> tokens;
  for (size_t i = 0; i <= children().size(); ++i) {
    if (i == drop_index) {
      tokens.push_back(dragged);
    }
    if (i == children().size()) {
      break;
    }
    std::string token = GetItemToken(children()[i]);
    if (!token.empty() && token != dragged) {
      tokens.push_back(std::move(token));
    }
  }
  return base::BindOnce(
      [](base::WeakPtr<Profile> profile, base::ListValue items,
         const ui::DropTargetEvent& event,
         ui::mojom::DragOperation& output_drag_op,
         std::unique_ptr<ui::LayerTreeOwner> drag_image_layer_owner) {
        if (profile) {
          profile->GetPrefs()->SetList(prefs::kToolbarItems, std::move(items));
          output_drag_op = ui::mojom::DragOperation::kMove;
        }
      },
      browser_->GetProfile()->GetWeakPtr(),
      WithAbsentItems(std::move(tokens)));
}

void ToolbarView::WriteDragDataForView(views::View* sender,
                                       const gfx::Point& press_pt,
                                       ui::OSExchangeData* data) {
  auto* const button = static_cast<ToolbarButton*>(sender);
  data->provider().SetDragImage(button->GetImage(button->GetState()),
                                press_pt.OffsetFromOrigin());
  // A handle inside an item (the extensions button) drags the item.
  views::View* item = sender;
  while (item->parent() != this) {
    item = item->parent();
  }
  base::Pickle pickle;
  pickle.WriteString(GetItemToken(item));
  data->SetPickledData(GetToolbarItemFormatType(), pickle);
}

int ToolbarView::GetDragOperationsForView(views::View* sender,
                                          const gfx::Point& p) {
  return ui::DragDropTypes::DRAG_MOVE;
}

bool ToolbarView::CanStartDragForView(views::View* sender,
                                      const gfx::Point& press_pt,
                                      const gfx::Point& p) {
  return true;
}

void ToolbarView::OnWillStartDragForView(views::View* dragged_view) {
  // Holding back or forward opens their history menu after a delay.
  static_cast<ToolbarButton*>(dragged_view)->ClearPendingMenu();
}

void ToolbarView::OnPaint(gfx::Canvas* canvas) {
  AccessiblePaneView::OnPaint(canvas);
  if (!drop_x_) {
    return;
  }
  constexpr int kIndicatorWidth = 2;
  const int height = GetLayoutConstant(LayoutConstant::kToolbarButtonHeight);
  canvas->FillRect(
      gfx::Rect(GetMirroredXWithWidthInView(*drop_x_ - kIndicatorWidth / 2,
                                            kIndicatorWidth),
                (this->height() - height) / 2, kIndicatorWidth, height),
      GetColorProvider()->GetColor(kColorToolbarButtonIcon));
}
