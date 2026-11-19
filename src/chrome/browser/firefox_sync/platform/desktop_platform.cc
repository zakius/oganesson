// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Firefox Sync's desktop side (see dubna's firefox_sync_platform.h).

#include <memory>
#include <algorithm>
#include <string>
#include <utility>
#include <vector>

#include "base/base_paths.h"
#include "base/containers/span.h"
#include "base/functional/bind.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/scoped_observation.h"
#include "base/path_service.h"
#include "base/strings/string_number_conversions.h"
#include "base/strings/utf_string_conversions.h"
#include "chrome/browser/browser_process.h"
#include "chrome/browser/firefox_sync/firefox_sync_platform.h"
#include "chrome/browser/firefox_sync/firefox_sync_service.h"
#include "chrome/browser/firefox_sync/firefox_sync_service_factory.h"
#include "chrome/browser/firefox_sync/platform/push_connection.h"
#include "chrome/browser/firefox_sync/platform/tabs_adapter.h"
#include "chrome/browser/notifications/notification_display_service.h"
#include "chrome/browser/notifications/notification_display_service_factory.h"
#include "chrome/browser/notifications/notification_handler.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/profiles/profile_attributes_entry.h"
#include "chrome/browser/profiles/profile_attributes_storage.h"
#include "chrome/browser/profiles/profile_manager.h"
#include "chrome/browser/ui/browser_window/public/browser_collection_observer.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/browser_window/public/global_browser_collection.h"
#include "chrome/browser/ui/browser_window/public/profile_browser_collection.h"
#include "chrome/browser/ui/navigator/browser_navigator.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "chrome/common/oganesson_pref_names.h"
#include "components/prefs/pref_change_registrar.h"
#include "components/prefs/pref_service.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/grit/oganesson_strings.h"
#include "build/build_config.h"
#include "components/sync_device_info/local_device_info_util.h"
#include "content/public/browser/web_contents.h"
#include "content/public/browser/web_contents_delegate.h"
#include "services/data_decoder/public/cpp/decode_image.h"
#include "third_party/skia/include/core/SkBitmap.h"

#if BUILDFLAG(IS_LINUX)
#include "crypto/nss_util.h"
#endif
#include "ui/base/l10n/l10n_util.h"
#include "ui/gfx/image/image.h"
#include "ui/message_center/public/cpp/notification.h"
#include "ui/message_center/public/cpp/notification_delegate.h"
#include "ui/message_center/public/cpp/notifier_id.h"
#include "url/gurl.h"

namespace firefox_sync {

namespace {

// The decoded picture's limit in bytes, as the download's.
constexpr size_t kMaxPictureSize = 4 * 1024 * 1024;

constexpr char kReceivedTabNotifier[] = "oganesson.firefox_sync.received_tab";

// Switches to the received tab, if it's still open.
void ActivateTab(base::WeakPtr<content::WebContents> contents) {
  if (contents && contents->GetDelegate()) {
    contents->GetDelegate()->ActivateContents(contents.get());
  }
}

class DesktopPlatform : public Platform, public BrowserCollectionObserver {
 public:
  explicit DesktopPlatform(Profile* profile)
      : profile_(profile) {
    browsers_.Observe(GlobalBrowserCollection::GetInstance());
    instant_tabs_.Init(profile_->GetPrefs());
    instant_tabs_.Add(prefs::kFirefoxSyncInstantTabs,
                      base::BindRepeating(&DesktopPlatform::UpdatePush,
                                          base::Unretained(this)));
  }

  void OnSignedIn(bool signed_in) override {
    signed_in_ = signed_in;
    UpdatePush();
  }

  // A window of the profile came to the front: tabs other devices sent show
  // up then, not only at the next sync or receive interval.
  void OnBrowserActivated(BrowserWindowInterface* browser) override {
    if (browser->GetProfile() != profile_) {
      return;
    }
    if (FirefoxSyncService* service =
            FirefoxSyncServiceFactory::GetForProfile(profile_)) {
      service->PollCommands();
    }
  }

  std::unique_ptr<SyncAdapter> CreateTabsAdapter(
      base::RepeatingClosure local_changed) override {
    return std::make_unique<TabsAdapter>(profile_, std::move(local_changed));
  }

  content::WebContents* OpenTab(const GURL& url) override {
    NavigateParams params(profile_, url, ui::PAGE_TRANSITION_LINK);
    params.disposition = WindowOpenDisposition::kNewForegroundTab;
    Navigate(&params);
    return params.navigated_or_inserted_contents.get();
  }

  // In the background, as Firefox does, with a notification that switches to
  // it.
  void OpenReceivedTab(const std::string& from,
                       const GURL& url,
                       const std::string& title) override {
    NavigateParams params(profile_, url, ui::PAGE_TRANSITION_LINK);
    params.disposition = WindowOpenDisposition::kNewBackgroundTab;
    Navigate(&params);
    content::WebContents* contents = params.navigated_or_inserted_contents.get();
    if (!contents) {
      return;
    }
    message_center::Notification notification(
        message_center::NOTIFICATION_TYPE_SIMPLE,
        kReceivedTabNotifier + base::NumberToString(++notifications_),
        l10n_util::GetStringFUTF16(IDS_OGANESSON_RECEIVED_TAB,
                                   base::UTF8ToUTF16(from)),
        base::UTF8ToUTF16(title), ui::ImageModel(), std::u16string(), url,
        message_center::NotifierId(
            message_center::NotifierType::SYSTEM_COMPONENT,
            kReceivedTabNotifier),
        {},
        base::MakeRefCounted<message_center::HandleNotificationClickDelegate>(
            base::BindRepeating(&ActivateTab, contents->GetWeakPtr())));
    NotificationDisplayServiceFactory::GetForProfile(profile_)->Display(
        NotificationHandler::Type::TRANSIENT, notification,
        /*metadata=*/nullptr);
  }

  // Every open tab at one of `urls`, as tennessine does: Firefox names tabs
  // only by URL, so copies of a tab can't be told apart.
  void CloseTabs(const std::string& from,
                 const std::vector<GURL>& urls) override {
    std::vector<base::WeakPtr<content::WebContents>> to_close;
    ProfileBrowserCollection::GetForProfile(profile_)->ForEach(
        [&](BrowserWindowInterface* browser) {
          if (browser->GetType() != BrowserWindowInterface::TYPE_NORMAL) {
            return true;
          }
          TabStripModel* model = browser->GetTabStripModel();
          for (int i = 0; i < model->count(); ++i) {
            content::WebContents* contents = model->GetWebContentsAt(i);
            if (std::ranges::contains(urls, contents->GetVisibleURL())) {
              to_close.push_back(contents->GetWeakPtr());
            }
          }
          return true;
        });
    for (const auto& contents : to_close) {
      if (contents) {
        contents->Close();
      }
    }
  }

  void ShowAccount(const std::string& name,
                   const std::string& url,
                   std::string picture,
                   bool keep_picture) override {
    // A picture still decoding is an older account's, or one signed out.
    decode_weak_factory_.InvalidateWeakPtrs();
    if (picture.empty()) {
      SetProfileAccount(name, url, keep_picture, SkBitmap());
      return;
    }
    data_decoder::DecodeImageIsolated(
        base::as_byte_span(picture), data_decoder::mojom::ImageCodec::kDefault,
        /*shrink_to_fit=*/true, kMaxPictureSize, gfx::Size(),
        base::BindOnce(&DesktopPlatform::SetProfileAccount,
                       decode_weak_factory_.GetWeakPtr(), name, url,
                       /*keep_picture=*/false));
  }

 private:
  // The browser profile shows the account like a Google one: the avatar
  // button, the profile menu and Settings show its picture, and its name
  // where the profile has none of its own. An empty bitmap removes the
  // picture.
  void SetProfileAccount(const std::string& name,
                         const std::string& url,
                         bool keep_picture,
                         const SkBitmap& picture) {
    ProfileAttributesEntry* entry =
        g_browser_process->profile_manager()
            ->GetProfileAttributesStorage()
            .GetProfileAttributesWithPath(profile_->GetPath());
    if (!entry) {
      return;
    }
    entry->SetGAIAName(base::UTF8ToUTF16(name));
    if (keep_picture) {
      return;
    }
    gfx::Image image = picture.drawsNothing()
                           ? gfx::Image()
                           : gfx::Image::CreateFrom1xBitmap(picture);
    entry->SetGAIAPicture(url, image);
    entry->SetIsUsingGAIAPicture(!image.IsEmpty());
  }

  // The push connection runs while signed in with Receive tabs instantly on.
  void UpdatePush() {
    const bool wanted =
        signed_in_ &&
        profile_->GetPrefs()->GetBoolean(prefs::kFirefoxSyncInstantTabs);
    if (wanted == !!push_) {
      return;
    }
    if (!wanted) {
      push_.reset();
      if (FirefoxSyncService* service = Service()) {
        service->SetPushEndpoint(std::string());
      }
      return;
    }
    push_ = std::make_unique<PushConnection>(
        profile_,
        base::BindRepeating(&DesktopPlatform::OnPushEndpoint,
                            weak_factory_.GetWeakPtr()),
        base::BindRepeating(&DesktopPlatform::OnPushNotice,
                            weak_factory_.GetWeakPtr()));
  }

  void OnPushEndpoint(const std::string& endpoint) {
    if (FirefoxSyncService* service = Service()) {
      service->SetPushEndpoint(endpoint);
    }
  }

  void OnPushNotice() {
    if (FirefoxSyncService* service = Service()) {
      service->OnPushReceived();
    }
  }

  // The service that owns this. Not called while it's being made: the push
  // connection's callbacks come later.
  FirefoxSyncService* Service() {
    return FirefoxSyncServiceFactory::GetForProfile(profile_);
  }

  const raw_ptr<Profile> profile_;
  bool signed_in_ = false;
  PrefChangeRegistrar instant_tabs_;
  std::unique_ptr<PushConnection> push_;
  // For each received tab's notification id.
  int notifications_ = 0;
  base::ScopedObservation<GlobalBrowserCollection, BrowserCollectionObserver>
      browsers_{this};
  base::WeakPtrFactory<DesktopPlatform> decode_weak_factory_{this};
  base::WeakPtrFactory<DesktopPlatform> weak_factory_{this};
};

}  // namespace

std::unique_ptr<Platform> CreatePlatform(Profile* profile) {
  return std::make_unique<DesktopPlatform>(profile);
}

base::FilePath SyncLibraryPath() {
  base::FilePath dir;
  base::PathService::Get(base::DIR_MODULE, &dir);
#if BUILDFLAG(IS_WIN)
  // Next to chrome.dll, with the NSS DLLs it loads; it initializes NSS itself,
  // which Chromium doesn't use on Windows.
  return dir.Append(FILE_PATH_LITERAL("oganesson_sync.dll"));
#else
  // Chromium's own NSS setup first; the library then uses it as is.
  crypto::EnsureNSSInit();
  return dir.Append(FILE_PATH_LITERAL("liboganesson_sync.so"));
#endif
}

std::string DeviceName() {
  // The hostname, or the Linux distribution's name for a "localhost"; the
  // computer's name on Windows. Chrome's own Sync names devices so.
  return "oganesson on " + syncer::GetPersonalizableDeviceNameBlocking();
}

}  // namespace firefox_sync
