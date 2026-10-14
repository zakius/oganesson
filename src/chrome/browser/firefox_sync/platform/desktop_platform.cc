// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Firefox Sync's desktop side (see dubna's firefox_sync_platform.h).

#include <memory>
#include <string>
#include <utility>

#include "base/base_paths.h"
#include "base/containers/span.h"
#include "base/functional/bind.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/path_service.h"
#include "base/strings/utf_string_conversions.h"
#include "chrome/browser/browser_process.h"
#include "chrome/browser/firefox_sync/firefox_sync_platform.h"
#include "chrome/browser/firefox_sync/platform/remote_tabs.h"
#include "chrome/browser/firefox_sync/platform/tabs_adapter.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/profiles/profile_attributes_entry.h"
#include "chrome/browser/profiles/profile_attributes_storage.h"
#include "chrome/browser/profiles/profile_manager.h"
#include "chrome/browser/ui/navigator/browser_navigator.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "crypto/nss_util.h"
#include "services/data_decoder/public/cpp/decode_image.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "ui/gfx/image/image.h"
#include "url/gurl.h"

namespace firefox_sync {

namespace {

// The decoded picture's limit in bytes, as the download's.
constexpr size_t kMaxPictureSize = 4 * 1024 * 1024;

class DesktopPlatform : public Platform {
 public:
  explicit DesktopPlatform(Profile* profile)
      : profile_(profile), remote_tabs_(profile) {}

  std::unique_ptr<SyncAdapter> CreateTabsAdapter(
      base::RepeatingClosure local_changed) override {
    return std::make_unique<TabsAdapter>(profile_, std::move(local_changed));
  }

  content::WebContents* OpenTab(const GURL& url) override {
    NavigateParams params(profile_, url, ui::PAGE_TRANSITION_LINK);
    params.disposition = WindowOpenDisposition::NEW_FOREGROUND_TAB;
    Navigate(&params);
    return params.navigated_or_inserted_contents.get();
  }

  void ShowRemoteTabs(const base::ListValue& devices) override {
    remote_tabs_.Update(devices);
  }

  void ClearRemoteTabs() override { remote_tabs_.Clear(); }

  void ShowAccount(const std::string& name,
                   const std::string& url,
                   std::string picture,
                   bool keep_picture) override {
    if (picture.empty()) {
      SetProfileAccount(name, url, keep_picture, SkBitmap());
      return;
    }
    data_decoder::DecodeImageIsolated(
        base::as_byte_span(picture), data_decoder::mojom::ImageCodec::kDefault,
        /*shrink_to_fit=*/true, kMaxPictureSize, gfx::Size(),
        base::BindOnce(&DesktopPlatform::SetProfileAccount,
                       weak_factory_.GetWeakPtr(), name, url,
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

  const raw_ptr<Profile> profile_;
  // The synced tabs for History, Recent tabs and the sessions API.
  RemoteTabs remote_tabs_;
  base::WeakPtrFactory<DesktopPlatform> weak_factory_{this};
};

}  // namespace

std::unique_ptr<Platform> CreatePlatform(Profile* profile) {
  return std::make_unique<DesktopPlatform>(profile);
}

base::FilePath SyncLibraryPath() {
  // Chromium's own NSS setup first; the library then uses it as is.
  crypto::EnsureNSSInit();
  base::FilePath dir;
  base::PathService::Get(base::DIR_MODULE, &dir);
  return dir.Append(FILE_PATH_LITERAL("liboganesson_sync.so"));
}

}  // namespace firefox_sync
