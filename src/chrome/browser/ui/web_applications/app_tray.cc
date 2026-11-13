// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/ui/web_applications/app_tray.h"

#include <algorithm>
#include <map>
#include <memory>
#include <set>
#include <utility>
#include <vector>

#include "base/functional/bind.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/no_destructor.h"
#include "base/strings/utf_string_conversions.h"
#include "base/values.h"
#include "chrome/browser/browser_process.h"
#include "chrome/browser/lifetime/browser_shutdown.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/status_icons/status_icon.h"
#include "chrome/browser/status_icons/status_icon_menu_model.h"
#include "chrome/browser/status_icons/status_icon_observer.h"
#include "chrome/browser/status_icons/status_tray.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/browser/ui/unload_controller.h"
#include "chrome/browser/web_applications/web_app_icon_manager.h"
#include "chrome/browser/web_applications/web_app_provider.h"
#include "chrome/browser/web_applications/web_app_registrar.h"
#include "chrome/grit/oganesson_strings.h"
#include "components/prefs/pref_service.h"
#include "components/prefs/scoped_user_pref_update.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/web_contents.h"
#include "content/public/common/referrer.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkCanvas.h"
#include "third_party/skia/include/core/SkColor.h"
#include "third_party/skia/include/core/SkImage.h"
#include "third_party/skia/include/core/SkPaint.h"
#include "ui/base/base_window.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/models/menu_separator_types.h"
#include "ui/base/page_transition_types.h"
#include "ui/gfx/image/image_skia.h"
#include "url/gurl.h"

namespace web_app {

namespace {

// Tray hosts scale it down to their panel's size.
constexpr int kIconSize = 64;
// Menu command ids: the manifest's shortcuts take 0 to n - 1.
constexpr int kQuitCommand = 1000;

using AppKey = std::pair<Profile*, webapps::AppId>;

// The apps with a badge, also without an open window.
std::set<AppKey>& Badged() {
  static base::NoDestructor<std::set<AppKey>> badged;
  return *badged;
}

// The icon with a red dot in its corner: at a panel's size, a count wouldn't
// be legible. The dock's icon shows the count (badge_manager_delegate_linux).
gfx::ImageSkia BadgedIcon(const SkBitmap& icon, bool badged) {
  if (!badged) {
    return gfx::ImageSkia::CreateFrom1xBitmap(icon);
  }
  SkBitmap bitmap;
  bitmap.allocN32Pixels(icon.width(), icon.height());
  bitmap.eraseColor(SK_ColorTRANSPARENT);
  SkCanvas canvas(bitmap);
  canvas.drawImage(icon.asImage(), 0, 0);
  SkPaint paint;
  paint.setAntiAlias(true);
  const float radius = icon.width() * 0.22f;
  paint.setColor(SK_ColorWHITE);
  canvas.drawCircle(icon.width() - radius, radius, radius, paint);
  paint.setColor(SkColorSetRGB(0xd9, 0x30, 0x25));
  canvas.drawCircle(icon.width() - radius, radius, radius * 0.75f, paint);
  return gfx::ImageSkia::CreateFrom1xBitmap(bitmap);
}

// A web app's open windows, never none, and its tray icon while it is a tray
// app.
class TrayApp : public StatusIconObserver,
                public StatusIconMenuModel::Delegate {
 public:
  TrayApp(Profile* profile, webapps::AppId app_id)
      : profile_(profile), app_id_(std::move(app_id)) {}

  ~TrayApp() override { RemoveIcon(); }

  std::vector<raw_ptr<BrowserWindowInterface>>& windows() { return windows_; }

  // Adds the icon for a tray app, or removes it.
  void Update() {
    if (!IsTrayApp(*profile_->GetPrefs(), app_id_)) {
      RemoveIcon();
      return;
    }
    if (status_icon_ || reading_icon_) {
      return;
    }
    WebAppProvider* provider = WebAppProvider::GetForWebApps(profile_);
    if (!provider) {
      return;
    }
    reading_icon_ = true;
    provider->icon_manager().ReadIconAndResize(
        app_id_, IconPurpose::ANY, kIconSize,
        base::BindOnce(&TrayApp::OnIconRead, weak_factory_.GetWeakPtr()));
  }

  void UpdateBadge() {
    if (status_icon_) {
      status_icon_->SetImage(BadgedIcon(
          icon_, Badged().contains(AppKey(profile_.get(), app_id_))));
    }
  }

  // Shows and activates the last window opened.
  void Show() {
    windows_.back()->GetWindow()->Show();
    windows_.back()->GetWindow()->Activate();
  }

  // StatusIconObserver:
  void OnStatusIconClicked() override { Show(); }

  // StatusIconMenuModel::Delegate:
  void ExecuteCommand(int command_id, int event_flags) override {
    if (command_id == kQuitCommand) {
      quitting_ = true;
      // A copy: the last window's close destroys this TrayApp.
      for (BrowserWindowInterface* browser :
           std::vector<raw_ptr<BrowserWindowInterface>>(windows_)) {
        browser->GetWindow()->Close();
      }
      return;
    }
    // In the open window, not in a new one as the desktop entry's actions do.
    GURL url = shortcut_urls_[command_id];
    Show();
    if (content::WebContents* contents =
            windows_.back()->GetTabStripModel()->GetActiveWebContents()) {
      contents->GetController().LoadURL(url, content::Referrer(),
                                        ui::PAGE_TRANSITION_AUTO_BOOKMARK,
                                        std::string());
    }
  }

  bool quitting() const { return quitting_; }

 private:
  void OnIconRead(OrderedSizeToBitmap bitmaps) {
    reading_icon_ = false;
    if (bitmaps.empty() || !IsTrayApp(*profile_->GetPrefs(), app_id_)) {
      return;
    }
    StatusTray* tray = g_browser_process->status_tray();
    WebAppProvider* provider = WebAppProvider::GetForWebApps(profile_);
    if (!tray || !provider) {
      return;
    }
    icon_ = bitmaps.begin()->second;
    const WebAppRegistrar& registrar = provider->registrar_unsafe();
    // With its badge at once: a second image right after would replace the
    // first while the tray still loads it.
    status_icon_ = tray->CreateStatusIcon(
        StatusTray::OTHER_ICON,
        BadgedIcon(icon_, Badged().contains(AppKey(profile_.get(), app_id_))),
        base::UTF8ToUTF16(registrar.GetAppShortName(app_id_)));
    if (!status_icon_) {
      return;
    }
    // Before the menu: on Linux, the menu then starts with an item that
    // shows the app, for trays whose click opens the menu.
    status_icon_->AddObserver(this);
    auto menu = std::make_unique<StatusIconMenuModel>(this);
    shortcut_urls_.clear();
    for (const WebAppShortcutsMenuItemInfo& shortcut :
         registrar.GetAppShortcutsMenuItemInfos(app_id_)) {
      menu->AddItem(shortcut_urls_.size(), shortcut.name);
      shortcut_urls_.push_back(shortcut.url);
    }
    if (!shortcut_urls_.empty()) {
      menu->AddSeparator(ui::NORMAL_SEPARATOR);
    }
    menu->AddItem(kQuitCommand,
                  l10n_util::GetStringUTF16(IDS_OGANESSON_TRAY_QUIT));
    status_icon_->SetContextMenu(std::move(menu));
  }

  void RemoveIcon() {
    weak_factory_.InvalidateWeakPtrs();
    reading_icon_ = false;
    if (!status_icon_) {
      return;
    }
    StatusIcon* icon = status_icon_;
    status_icon_ = nullptr;
    icon->RemoveObserver(this);
    g_browser_process->status_tray()->RemoveStatusIcon(icon);
  }

  raw_ptr<Profile> profile_;
  const webapps::AppId app_id_;
  std::vector<raw_ptr<BrowserWindowInterface>> windows_;
  SkBitmap icon_;
  std::vector<GURL> shortcut_urls_;
  raw_ptr<StatusIcon> status_icon_ = nullptr;
  bool reading_icon_ = false;
  bool quitting_ = false;
  base::WeakPtrFactory<TrayApp> weak_factory_{this};
};

std::map<AppKey, std::unique_ptr<TrayApp>>& Apps() {
  static base::NoDestructor<std::map<AppKey, std::unique_ptr<TrayApp>>> apps;
  return *apps;
}

TrayApp* FindTrayApp(Profile* profile, const webapps::AppId& app_id) {
  auto it = Apps().find(AppKey(profile, app_id));
  return it == Apps().end() ? nullptr : it->second.get();
}

std::map<AppKey, std::unique_ptr<TrayApp>>::iterator FindWindow(
    BrowserWindowInterface* browser) {
  for (auto it = Apps().begin(); it != Apps().end(); ++it) {
    if (std::ranges::contains(it->second->windows(), browser)) {
      return it;
    }
  }
  return Apps().end();
}

}  // namespace

bool IsTrayApp(const PrefService& prefs, const webapps::AppId& app_id) {
  return prefs.GetDict(kTrayApps).FindBool(app_id).value_or(false);
}

void SetTrayApp(Profile* profile, const webapps::AppId& app_id, bool enabled) {
  {
    ScopedDictPrefUpdate update(profile->GetPrefs(), kTrayApps);
    if (enabled) {
      update->Set(app_id, true);
    } else {
      update->Remove(app_id);
    }
  }
  TrayApp* app = FindTrayApp(profile, app_id);
  if (!app) {
    return;
  }
  // A window hidden in the tray would have no way back.
  if (!enabled) {
    for (BrowserWindowInterface* browser : app->windows()) {
      if (!browser->GetWindow()->IsVisible()) {
        browser->GetWindow()->Show();
      }
    }
  }
  app->Update();
}

void OnAppWindowCreated(BrowserWindowInterface* browser,
                        const webapps::AppId& app_id) {
  // Not the app's popups.
  if (browser->GetType() != BrowserWindowInterface::TYPE_APP) {
    return;
  }
  std::unique_ptr<TrayApp>& app =
      Apps()[AppKey(browser->GetProfile(), app_id)];
  if (!app) {
    app = std::make_unique<TrayApp>(browser->GetProfile(), app_id);
  }
  app->windows().push_back(browser);
  app->Update();
}

void OnAppWindowDestroyed(BrowserWindowInterface* browser) {
  auto it = FindWindow(browser);
  if (it == Apps().end()) {
    return;
  }
  std::erase(it->second->windows(), browser);
  if (it->second->windows().empty()) {
    Apps().erase(it);
  }
}

bool MaybeHideToTray(BrowserWindowInterface* browser) {
  auto it = FindWindow(browser);
  if (it == Apps().end() || it->second->windows().size() != 1 ||
      it->second->quitting() || browser_shutdown::IsTryingToQuit() ||
      !IsTrayApp(*browser->GetProfile()->GetPrefs(), it->first.second)) {
    return false;
  }
  // Uninstalling, and other closes by the browser itself, skip the warning.
  UnloadController* unload = UnloadController::From(browser);
  if (unload && unload->force_skip_warning_user_on_close()) {
    return false;
  }
  browser->GetWindow()->Hide();
  return true;
}

void ShowFromTray(BrowserWindowInterface* browser) {
  auto it = FindWindow(browser);
  if (it != Apps().end() && !browser->GetWindow()->IsVisible() &&
      IsTrayApp(*browser->GetProfile()->GetPrefs(), it->first.second)) {
    browser->GetWindow()->Show();
    browser->GetWindow()->Activate();
  }
}

void SetAppTrayBadge(Profile* profile,
                     const webapps::AppId& app_id,
                     bool badged) {
  if (badged) {
    Badged().insert(AppKey(profile, app_id));
  } else {
    Badged().erase(AppKey(profile, app_id));
  }
  if (TrayApp* app = FindTrayApp(profile, app_id)) {
    app->UpdateBadge();
  }
}

}  // namespace web_app
