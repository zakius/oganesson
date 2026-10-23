// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_FIREFOX_SYNC_PLATFORM_SEND_TO_DEVICE_MENU_H_
#define CHROME_BROWSER_FIREFOX_SYNC_PLATFORM_SEND_TO_DEVICE_MENU_H_

#include <memory>
#include <string>
#include <vector>

#include "base/memory/raw_ptr.h"
#include "ui/menus/simple_menu_model.h"
#include "url/gurl.h"

class Profile;

namespace firefox_sync {

// "Send to device ▸" in the page, link and tab context menus: the Mozilla
// account's other devices that take tabs, Firefox ones included, then "All
// devices".
class SendToDeviceMenu : public ui::SimpleMenuModel::Delegate {
 public:
  struct Page {
    GURL url;
    std::string title;
  };

  // Adds the submenu to `menu` as `command_id`, after a separator with
  // `add_separator`, and keeps it in `slot`, which must live as long as
  // `menu`. Adds nothing and returns false when there's no device to send to,
  // or no web page among `pages`.
  static bool AppendTo(ui::SimpleMenuModel* menu,
                       int command_id,
                       Profile* profile,
                       std::vector<Page> pages,
                       std::unique_ptr<SendToDeviceMenu>& slot,
                       bool add_separator = false);

  SendToDeviceMenu(const SendToDeviceMenu&) = delete;
  SendToDeviceMenu& operator=(const SendToDeviceMenu&) = delete;
  ~SendToDeviceMenu() override;

  // ui::SimpleMenuModel::Delegate:
  void ExecuteCommand(int command_id, int event_flags) override;

 private:
  SendToDeviceMenu(Profile* profile, std::vector<Page> pages);

  void Send(const std::string& device_id);

  const raw_ptr<Profile> profile_;
  const std::vector<Page> pages_;
  // By item, from the first device's command id on.
  std::vector<std::string> device_ids_;
  ui::SimpleMenuModel model_{this};
};

}  // namespace firefox_sync

#endif  // CHROME_BROWSER_FIREFOX_SYNC_PLATFORM_SEND_TO_DEVICE_MENU_H_
