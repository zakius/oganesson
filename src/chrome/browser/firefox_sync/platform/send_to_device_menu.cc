// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/firefox_sync/platform/send_to_device_menu.h"

#include <utility>

#include "base/memory/ptr_util.h"

#include "base/strings/utf_string_conversions.h"
#include "chrome/app/chrome_command_ids.h"
#include "chrome/app/vector_icons/vector_icons.h"
#include "chrome/browser/firefox_sync/firefox_sync_service.h"
#include "chrome/browser/firefox_sync/firefox_sync_service_factory.h"
#include "chrome/grit/generated_resources.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/models/image_model.h"
#include "ui/base/ui_base_features.h"

namespace firefox_sync {

// static
bool SendToDeviceMenu::AppendTo(ui::SimpleMenuModel* menu,
                                int command_id,
                                Profile* profile,
                                std::vector<Page> pages,
                                std::unique_ptr<SendToDeviceMenu>& slot,
                                bool add_separator) {
  // Only web pages: the receiving browser opens nothing else.
  std::erase_if(pages, [](const Page& page) {
    return !page.url.SchemeIsHTTPOrHTTPS();
  });
  // Null for incognito and guest profiles, which send nothing.
  FirefoxSyncService* service = FirefoxSyncServiceFactory::GetForProfile(profile);
  if (pages.empty() || !service) {
    return false;
  }
  auto submenu = base::WrapUnique(new SendToDeviceMenu(profile, std::move(pages)));
  for (const base::Value& value : service->devices()) {
    const int next = IDC_OGANESSON_SEND_TO_DEVICE_FIRST +
                     static_cast<int>(submenu->device_ids_.size());
    if (next > IDC_OGANESSON_SEND_TO_DEVICE_LAST) {
      break;
    }
    const base::DictValue* device = value.GetIfDict();
    const std::string* id = device ? device->FindString("id") : nullptr;
    const std::string* name = device ? device->FindString("name") : nullptr;
    if (id && name && device->FindBool("sendTab").value_or(false)) {
      submenu->model_.AddItem(next, base::UTF8ToUTF16(*name));
      submenu->device_ids_.push_back(*id);
    }
  }
  if (submenu->device_ids_.empty()) {
    return false;
  }
  if (submenu->device_ids_.size() > 1) {
    submenu->model_.AddSeparator(ui::NORMAL_SEPARATOR);
    submenu->model_.AddItemWithStringId(IDC_OGANESSON_SEND_TO_ALL_DEVICES,
                                        IDS_OGANESSON_SEND_TO_ALL_DEVICES);
  }
  slot = std::move(submenu);
  if (add_separator) {
    menu->AddSeparator(ui::NORMAL_SEPARATOR);
  }
  menu->AddSubMenuWithStringIdAndIcon(
      command_id, IDS_OGANESSON_SEND_TO_DEVICE, &slot->model_,
      ui::ImageModel::FromVectorIcon(features::IsRoundedIconsEnabled()
                                         ? kDevicesIcon
                                         : kDevicesOldIcon));
  return true;
}

SendToDeviceMenu::SendToDeviceMenu(Profile* profile, std::vector<Page> pages)
    : profile_(profile), pages_(std::move(pages)) {}

SendToDeviceMenu::~SendToDeviceMenu() = default;

void SendToDeviceMenu::ExecuteCommand(int command_id, int event_flags) {
  if (command_id == IDC_OGANESSON_SEND_TO_ALL_DEVICES) {
    for (const std::string& id : device_ids_) {
      Send(id);
    }
    return;
  }
  const size_t index = command_id - IDC_OGANESSON_SEND_TO_DEVICE_FIRST;
  if (index < device_ids_.size()) {
    Send(device_ids_[index]);
  }
}

void SendToDeviceMenu::Send(const std::string& device_id) {
  FirefoxSyncService* service =
      FirefoxSyncServiceFactory::GetForProfile(profile_);
  if (!service) {
    return;
  }
  for (const Page& page : pages_) {
    service->SendTab(device_id, page.url, page.title);
  }
}

}  // namespace firefox_sync
