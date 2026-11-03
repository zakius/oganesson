// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/views/frame/mouse_gesture_event_rewriter.h"

#include "build/build_config.h"

#if BUILDFLAG(IS_LINUX) || BUILDFLAG(IS_WIN)

#include <cmath>
#include <memory>
#include <string>
#include <string_view>
#include <utility>

#include "base/functional/bind.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/scoped_observation.h"
#include "base/task/single_thread_task_runner.h"
#include "base/values.h"
#include "chrome/browser/extensions/commands/command_service.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser_commands.h"
#include "chrome/browser/ui/browser_shortcuts/browser_shortcut_service_factory.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/browser/ui/tabs/tab_strip_model_observer.h"
#include "chrome/browser/ui/extensions/extensions_toolbar_view_model.h"
#include "chrome/browser/ui/toolbar/toolbar_action_view_model.h"
#include "chrome/browser/ui/views/extensions/extension_keybinding_registry_views.h"
#include "chrome/browser/ui/views/extensions/extensions_toolbar_desktop.h"
#include "chrome/browser/ui/views/frame/browser_view.h"
#include "chrome/browser/ui/views/frame/mouse_gesture_tracker.h"
#include "chrome/browser/ui/views/toolbar/toolbar_view.h"
#include "chrome/common/oganesson_pref_names.h"
#include "components/prefs/pref_service.h"
#include "content/public/browser/render_widget_host_view.h"
#include "content/public/browser/web_contents.h"
#include "extensions/browser/extension_registry.h"
#include "extensions/common/manifest_constants.h"
#include "ui/aura/client/capture_client.h"
#include "ui/aura/client/capture_client_observer.h"
#include "ui/aura/window.h"
#include "ui/aura/window_observer.h"
#include "ui/aura/window_tree_host.h"
#include "ui/base/accelerators/command.h"
#include "ui/events/event.h"
#include "ui/events/event_rewriter.h"
#include "ui/base/class_property.h"
#include "ui/events/event_source.h"
#include "ui/views/view.h"
#include "ui/views/view_observer.h"
#include "ui/views/widget/widget.h"
#include "ui/views/widget/widget_observer.h"

namespace {

// A tab's dialog stays hidden while another tab shows, so only a shown dialog
// blocks the window.
bool WidgetHasChildModalDialog(views::Widget* parent_widget) {
  for (views::Widget* widget :
       views::Widget::GetAllChildWidgets(parent_widget->GetNativeView())) {
    if (widget != parent_widget && widget->IsModal() && widget->IsVisible()) {
      return true;
    }
  }
  return false;
}

class MouseGestureEventRewriterImpl : public ui::EventRewriter,
                                      public aura::WindowObserver,
                                      public aura::client::CaptureClientObserver,
                                      public views::ViewObserver,
                                      public views::WidgetObserver,
                                      public TabStripModelObserver {
 public:
  explicit MouseGestureEventRewriterImpl(BrowserView* browser_view)
      : browser_view_(browser_view) {
    view_observation_.Observe(browser_view);
    Attach();
  }

  ~MouseGestureEventRewriterImpl() override { Detach(); }

  // Watches `browser_view_`'s widget, window and tab strip, and takes its
  // window's input.
  void Attach() {
    views::Widget* const widget = browser_view_->GetWidget();
    if (!widget) {
      return;
    }
    Detach();
    widget_observation_.Observe(widget);
    window_observation_.Observe(widget->GetNativeWindow());
    if (TabStripModel* tabs = browser_view_->browser()->GetTabStripModel()) {
      tabs->AddObserver(this);
      tab_strip_ = tabs;
    }
    AttachToRoot();
  }

  // Drops the gesture in progress, if any.
  void Cancel() {
    ++generation_;
    tracker_.Cancel();
    press_.reset();
    ReleaseCapture();
  }

  // Undoes Attach().
  void Detach() {
    DetachFromRoot();
    window_observation_.Reset();
    widget_observation_.Reset();
    if (tab_strip_) {
      tab_strip_->RemoveObserver(this);
      tab_strip_ = nullptr;
    }
  }

 private:
  // Keys in prefs::kMouseGestures besides stroke chains such as "DR".
  static constexpr char kRockerLeftRight[] = "rocker-lr";  // Hold left.
  static constexpr char kRockerRightLeft[] = "rocker-rl";  // Hold right.
  static constexpr char kWheelUp[] = "wheel-up";
  static constexpr char kWheelDown[] = "wheel-down";

  bool SupportsNonRootLocation() const override { return true; }

  ui::EventDispatchDetails RewriteEvent(
      const ui::Event& event,
      const Continuation continuation) override {
    if (event.type() == ui::EventType::kMousePressed) {
      // A new press means a swallowed release was lost.
      swallow_releases_ &= ~event.AsMouseEvent()->changed_button_flags();
    } else if (event.type() == ui::EventType::kMouseReleased &&
               (swallow_releases_ &
                event.AsMouseEvent()->changed_button_flags())) {
      swallow_releases_ &= ~event.AsMouseEvent()->changed_button_flags();
      return DiscardEvent(continuation);
    }
    const bool right_press = event.type() == ui::EventType::kMousePressed &&
                             event.AsMouseEvent()->changed_button_flags() ==
                                 ui::EF_RIGHT_MOUSE_BUTTON;
    if (right_press) {
      auto weak = weak_factory_.GetWeakPtr();
      ReleaseCapture();
      if (!weak) {
        return DiscardEvent(continuation);
      }
      ++generation_;
      tracker_ = {};
      press_.reset();
      triggered_ = false;
      wheel_offset_ = 0;
      auto* contents = browser_view_->GetActiveWebContents();
      auto* view = contents ? contents->GetRenderWidgetHostView() : nullptr;
      // No gestures at all turns them off: the right button goes to pages,
      // and to add-ons with gestures of their own, such as Gesturefy.
      const bool eligible =
          !browser_view_->GetProfile()
               ->GetPrefs()
               ->GetDict(prefs::kMouseGestures)
               .empty() &&
          !event.IsControlDown() && !(event.flags() & ui::EF_IS_NON_CLIENT) &&
          browser_view_->GetWidget()->IsActive() && contents &&
          !(view && view->IsPointerLocked()) &&
          !WidgetHasChildModalDialog(browser_view_->GetWidget());
      // The held left button may own capture, so skip the capture check.
      if (eligible && (event.flags() & ui::EF_LEFT_MOUSE_BUTTON) &&
          PostCommand(kRockerLeftRight)) {
        swallow_releases_ |= ui::EF_RIGHT_MOUSE_BUTTON;
        return DiscardEvent(continuation);
      }
      if (!eligible || !event.AsMouseEvent()->IsOnlyRightMouseButton() ||
          capture_client_->GetGlobalCaptureWindow()) {
        return SendEvent(continuation, &event);
      }
      const auto point = Location(event);
      tracker_.Begin(point.x(), point.y());
      contents_ = contents->GetWeakPtr();
      press_ = std::make_unique<ui::MouseEvent>(*event.AsMouseEvent());
      owns_capture_ = true;
      weak = weak_factory_.GetWeakPtr();
      window_observation_.GetSource()->SetCapture();
      if (!weak) {
        return DiscardEvent(continuation);
      }
      if (!window_observation_.GetSource()->HasCapture()) {
        owns_capture_ = false;
        tracker_ = {};
        press_.reset();
        return SendEvent(continuation, &event);
      }
      return DiscardEvent(continuation);
    }

    if (!tracker_.active()) {
      return SendEvent(continuation, &event);
    }
    auto* active_contents = browser_view_->GetActiveWebContents();
    if (triggered_ && active_contents) {
      contents_ = active_contents->GetWeakPtr();
    } else if (!contents_ || contents_.get() != active_contents) {
      auto weak = weak_factory_.GetWeakPtr();
      Cancel();
      if (!weak) {
        return DiscardEvent(continuation);
      }
    }
    if (!tracker_.cancelled() && !triggered_ && event.IsControlDown()) {
      return ReplayPress(event, continuation);
    }
    // Once cancelled, Escape is for whatever took over, such as a menu that
    // took capture.
    if (event.type() == ui::EventType::kKeyPressed &&
        event.AsKeyEvent()->key_code() == ui::VKEY_ESCAPE &&
        !tracker_.cancelled()) {
      Cancel();
      return DiscardEvent(continuation);
    }
    if (!event.IsMouseEvent()) {
      return SendEvent(continuation, &event);
    }
    if (event.type() == ui::EventType::kMousePressed) {
      if (tracker_.cancelled()) {
        return SendEvent(continuation, &event);
      }
      const int button = event.AsMouseEvent()->changed_button_flags();
      // Every left click with right held runs the rocker command again.
      if ((button == ui::EF_LEFT_MOUSE_BUTTON &&
           PostCommand(kRockerRightLeft)) ||
          triggered_) {
        // The right press is never replayed once a command ran.
        triggered_ = true;
        press_.reset();
        swallow_releases_ |= button;
        return DiscardEvent(continuation);
      }
      return ReplayPress(event, continuation);
    }
    // Without the right button, its release went to a window that took
    // capture, such as a menu: the gesture is over. Wayland sends no motion
    // when that window closes, so a wheel can be the first to tell.
    if ((event.type() == ui::EventType::kMouseMoved ||
         event.type() == ui::EventType::kMouseDragged ||
         event.type() == ui::EventType::kMousewheel) &&
        !event.AsMouseEvent()->IsRightMouseButton()) {
      auto weak = weak_factory_.GetWeakPtr();
      Cancel();
      if (!weak) {
        return DiscardEvent(continuation);
      }
      tracker_ = {};
      return SendEvent(continuation, &event);
    }
    if (event.type() == ui::EventType::kMousewheel) {
      // Counts whole wheel notches, so smooth trackpad scrolling fires slowly.
      wheel_offset_ += event.AsMouseWheelEvent()->y_offset();
      while (!tracker_.cancelled() &&
             std::abs(wheel_offset_) >= ui::MouseWheelEvent::kWheelDelta) {
        const bool up = wheel_offset_ > 0;
        wheel_offset_ += up ? -ui::MouseWheelEvent::kWheelDelta
                            : ui::MouseWheelEvent::kWheelDelta;
        if (PostCommand(up ? kWheelUp : kWheelDown)) {
          triggered_ = true;
          press_.reset();
        }
      }
      return DiscardEvent(continuation);
    }
    if (event.type() == ui::EventType::kMouseReleased &&
        (event.AsMouseEvent()->changed_button_flags() &
         ui::EF_RIGHT_MOUSE_BUTTON)) {
      const auto point = Location(event);
      const std::string chain = tracker_.Finish(point.x(), point.y());
      const bool cancelled = tracker_.cancelled();
      if (!cancelled && !triggered_ && chain.empty()) {
        return ReplayPress(event, continuation);
      }
      press_.reset();
      auto weak = weak_factory_.GetWeakPtr();
      ReleaseCapture();
      if (!weak) {
        return DiscardEvent(continuation);
      }
      if (!cancelled && !triggered_) {
        PostCommand(chain);
      }
      return DiscardEvent(continuation);
    }
    if (event.type() == ui::EventType::kMouseReleased) {
      return SendEvent(continuation, &event);
    }
    if (event.type() == ui::EventType::kMouseMoved ||
        event.type() == ui::EventType::kMouseDragged) {
      const auto point = Location(event);
      tracker_.Update(point.x(), point.y());
    }
    return DiscardEvent(continuation);
  }

  gfx::PointF Location(const ui::Event& event) const {
    gfx::PointF point = event.AsLocatedEvent()->root_location_f();
    window_observation_.GetSource()->GetHost()->ConvertPixelsToDIP(&point);
    return point;
  }

  ui::EventDispatchDetails ReplayPress(const ui::Event& event,
                                     Continuation continuation) {
    auto press = std::move(press_);
    tracker_ = {};
    auto weak = weak_factory_.GetWeakPtr();
    ReleaseCapture();
    if (!weak) {
      return DiscardEvent(continuation);
    }
    if (press) {
      // Replay through the continuation to bypass only this interceptor.
      const auto details = SendEvent(continuation, press.get());
      if (details.dispatcher_destroyed || details.target_destroyed || !weak) {
        return details;
      }
    }
    return SendEvent(continuation, &event);
  }

  // Posts the command mapped to `gesture`, if any, so it runs after dispatch.
  // Values are browser command ids or {"extension": id, "command": name}.
  bool PostCommand(std::string_view gesture) {
    const base::Value* command = browser_view_->GetProfile()
                                     ->GetPrefs()
                                     ->GetDict(prefs::kMouseGestures)
                                     .Find(gesture);
    if (!command || !(command->is_int() || command->is_dict())) {
      return false;
    }
    base::SingleThreadTaskRunner::GetCurrentDefault()->PostTask(
        FROM_HERE, base::BindOnce(&MouseGestureEventRewriterImpl::RunCommand,
                                  weak_factory_.GetWeakPtr(), generation_,
                                  command->Clone()));
    return true;
  }

  // Tab changes bump `generation_` through Cancel() unless a mid-gesture
  // command caused them.
  void RunCommand(uint64_t generation, base::Value command) {
    if (generation != generation_ || !browser_view_->GetWidget()->IsActive()) {
      return;
    }
    BrowserWindowInterface* browser = browser_view_->browser();
    if (command.is_int()) {
      // Only run commands the shortcuts settings page exposes.
      auto* service =
          browser_shortcuts::BrowserShortcutServiceFactory::GetForProfile(
              browser_view_->GetProfile());
      if (service && service->HasCommand(command.GetInt()) &&
          chrome::IsCommandEnabled(browser, command.GetInt())) {
        chrome::ExecuteCommand(browser, command.GetInt());
      }
      return;
    }
    const std::string* extension_id = command.GetDict().FindString("extension");
    const std::string* name = command.GetDict().FindString("command");
    if (!extension_id || !name ||
        !extensions::ExtensionRegistry::Get(browser_view_->GetProfile())
             ->enabled_extensions()
             .Contains(*extension_id)) {
      return;
    }
    if (*name == extensions::manifest_values::kActionCommandEvent ||
        *name == extensions::manifest_values::kBrowserActionCommandEvent) {
      auto* container = browser_view_->toolbar()
                            ? browser_view_->toolbar()->extensions_container()
                            : nullptr;
      auto* action = container
                         ? container->GetToolbarViewModel()->GetActionForId(
                               *extension_id)
                         : nullptr;
      if (action) {
        action->ExecuteUserAction(
            ToolbarActionViewModel::InvocationSource::kCommand);
      }
      return;
    }
    ui::CommandMap commands;
    extensions::CommandService::Get(browser_view_->GetProfile())
        ->GetNamedCommands(*extension_id, extensions::CommandService::ALL,
                           extensions::CommandService::ANY_SCOPE, &commands);
    auto* registry = ExtensionKeybindingRegistryViews::From(browser);
    if (registry && commands.contains(*name)) {
      registry->ExecuteCommand(*extension_id, *name);
    }
  }

  void ReleaseCapture() {
    auto* window = window_observation_.GetSource();
    if (std::exchange(owns_capture_, false) && window && window->HasCapture()) {
      window->ReleaseCapture();
    }
  }

  void AttachToRoot() {
    auto* window = window_observation_.GetSource();
    if (!window || !window->GetRootWindow()) {
      return;
    }
    capture_client_ = aura::client::GetCaptureClient(window->GetRootWindow());
    if (!capture_client_) {
      return;
    }
    capture_client_->AddObserver(this);
    source_observation_.Observe(window->GetHost()->GetEventSource());
  }

  void DetachFromRoot() {
    Cancel();
    source_observation_.Reset();
    if (capture_client_) {
      capture_client_->RemoveObserver(this);
      capture_client_ = nullptr;
    }
  }

  void OnWindowRemovingFromRootWindow(aura::Window* window,
                                     aura::Window* new_root) override {
    DetachFromRoot();
  }

  void OnWindowAddedToRootWindow(aura::Window* window) override {
    AttachToRoot();
  }

  void OnWindowDestroying(aura::Window* window) override {
    DetachFromRoot();
    window_observation_.Reset();
  }

  // views::ViewObserver:
  void OnViewRemovedFromWidget(views::View* view) override { Detach(); }
  void OnViewIsDeleting(views::View* view) override {
    Detach();
    view_observation_.Reset();
  }

  // views::WidgetObserver:
  void OnWidgetActivationChanged(views::Widget* widget, bool active) override {
    if (!active) {
      Cancel();
    }
  }
  void OnWidgetBoundsChanged(views::Widget* widget,
                             const gfx::Rect& new_bounds) override {
    Cancel();
  }
  void OnWidgetDestroying(views::Widget* widget) override { Detach(); }

  // TabStripModelObserver: a tab switch cancels the gesture, unless a command
  // it fired, such as wheel tab cycling, switched tabs.
  void OnTabStripModelChanged(
      TabStripModel* tab_strip_model,
      const TabStripModelChange& change,
      const TabStripSelectionChange& selection) override {
    if (selection.active_tab_changed() && !triggered_) {
      Cancel();
    }
  }

  void OnCaptureChanged(aura::Window* lost_capture,
                        aura::Window* gained_capture) override {
    if (lost_capture == window_observation_.GetSource() && tracker_.active()) {
      owns_capture_ = false;
      Cancel();
    }
  }

  const raw_ptr<BrowserView> browser_view_;
  raw_ptr<aura::client::CaptureClient> capture_client_ = nullptr;
  base::ScopedObservation<aura::Window, aura::WindowObserver>
      window_observation_{this};
  base::ScopedObservation<views::View, views::ViewObserver> view_observation_{
      this};
  base::ScopedObservation<views::Widget, views::WidgetObserver>
      widget_observation_{this};
  raw_ptr<TabStripModel> tab_strip_ = nullptr;
  base::ScopedObservation<ui::EventSource, ui::EventRewriter>
      source_observation_{this};
  base::WeakPtr<content::WebContents> contents_;
  std::unique_ptr<ui::MouseEvent> press_;
  MouseGestureTracker tracker_;
  bool owns_capture_ = false;
  // Whether a rocker or wheel command ran during the current right press.
  bool triggered_ = false;
  int wheel_offset_ = 0;
  // Buttons whose next release belongs to a consumed press.
  int swallow_releases_ = 0;
  uint64_t generation_ = 0;
  base::WeakPtrFactory<MouseGestureEventRewriterImpl> weak_factory_{this};
};

}  // namespace

DEFINE_UI_CLASS_PROPERTY_TYPE(MouseGestureEventRewriterImpl*)

namespace {

// Owns a BrowserView's recognizer, so it lives as long as the view.
DEFINE_OWNED_UI_CLASS_PROPERTY_KEY(MouseGestureEventRewriterImpl,
                                   kMouseGestureRewriterKey)

}  // namespace

// static
void MouseGestureEventRewriter::AttachTo(BrowserView* browser_view) {
  if (auto* rewriter = browser_view->GetProperty(kMouseGestureRewriterKey)) {
    rewriter->Attach();
    return;
  }
  browser_view->SetProperty(
      kMouseGestureRewriterKey,
      std::make_unique<MouseGestureEventRewriterImpl>(browser_view));
}

#endif  // BUILDFLAG(IS_LINUX) || BUILDFLAG(IS_WIN)
