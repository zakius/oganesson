// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/badging/badge_manager_delegate_linux.h"

#include <optional>
#include <string>

#include "base/strings/strcat.h"
#include "chrome/browser/badging/badge_manager.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/shell_integration_linux.h"
#include "chrome/browser/web_applications/web_app_helpers.h"
#include "components/dbus/thread_linux/dbus_thread_linux.h"
#include "dbus/bus.h"
#include "dbus/exported_object.h"
#include "dbus/message.h"
#include "dbus/object_path.h"

namespace badging {

namespace {

constexpr char kInterface[] = "com.canonical.Unity.LauncherEntry";
constexpr char kSignalUpdate[] = "Update";
// Any path: docks listen to the signal from every object.
constexpr char kObjectPath[] = "/com/canonical/unity/launcherentry/oganesson";

void AppendProperty(dbus::MessageWriter& properties,
                    const char* name,
                    int64_t value) {
  dbus::MessageWriter entry(nullptr);
  properties.OpenDictEntry(&entry);
  entry.AppendString(name);
  entry.AppendVariantOfInt64(value);
  properties.CloseContainer(&entry);
}

void AppendProperty(dbus::MessageWriter& properties,
                    const char* name,
                    bool value) {
  dbus::MessageWriter entry(nullptr);
  properties.OpenDictEntry(&entry);
  entry.AppendString(name);
  entry.AppendVariantOfBool(value);
  properties.CloseContainer(&entry);
}

}  // namespace

BadgeManagerDelegateLinux::BadgeManagerDelegateLinux(
    Profile* profile,
    BadgeManager* badge_manager)
    : BadgeManagerDelegate(profile, badge_manager) {}

void BadgeManagerDelegateLinux::OnAppBadgeUpdated(
    const webapps::AppId& app_id) {
  scoped_refptr<dbus::Bus> bus = dbus_thread_linux::GetSharedSessionBus();
  if (!bus) {
    return;
  }
  // A flag badge has no count: only the tray icon shows it (app_tray.h).
  std::optional<BadgeManager::BadgeValue> badge =
      badge_manager()->GetBadgeValue(app_id);
  const int64_t count = badge && *badge ? static_cast<int64_t>(**badge) : 0;

  const std::string desktop_id = shell_integration_linux::GetXdgAppIdForWebApp(
      web_app::GenerateApplicationNameFromAppId(app_id), profile()->GetPath());
  dbus::Signal signal(kInterface, kSignalUpdate);
  dbus::MessageWriter writer(&signal);
  writer.AppendString(base::StrCat({"application://", desktop_id, ".desktop"}));
  dbus::MessageWriter properties(nullptr);
  writer.OpenArray("{sv}", &properties);
  AppendProperty(properties, "count", count);
  AppendProperty(properties, "count-visible", count > 0);
  writer.CloseContainer(&properties);
  bus->GetExportedObject(dbus::ObjectPath(kObjectPath))->SendSignal(&signal);
}

}  // namespace badging
