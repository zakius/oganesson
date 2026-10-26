// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_BROWSER_TRAFFIC_BROWSER_TRAFFIC_MONITOR_H_
#define CHROME_BROWSER_BROWSER_TRAFFIC_BROWSER_TRAFFIC_MONITOR_H_

#include <vector>

#include "base/functional/callback_forward.h"
#include "components/browser_traffic/browser_traffic.h"

class GURL;

// oganesson's side of browser traffic (dubna's components/browser_traffic):
// which rows it shows, the server's health check, and the certificate data's
// age, which badges the app menu (docs/helium-patch-decisions.md).
namespace browser_traffic {

// How browser updates show on the Browser traffic page.
enum class BrowserUpdates {
  kRow,             // a Windows per-user install: WinSparkle, a row
  kManaged,         // a Windows all-users install: read-only
  kPackageManager,  // Linux: a note
};
BrowserUpdates GetBrowserUpdates();

// The rows the page shows, which its presets set.
std::vector<Row> ShownRows();

// From the end of startup to shutdown: the hourly health check, the age of
// the certificate data, and the results of component update checks, which are
// the real fetches through the server. Tells the profiles' Helium code of
// every change: their prefs are derived from Local State.
void StartMonitor();
void StopMonitor();

// Asks `server`, a ParseServer() result, for helium-services' connectivity
// check. Records the answer when `server` is the one in use.
void CheckServer(const GURL& server, base::OnceCallback<void(bool)> callback);

// Updates the components of `row` (ComponentsOf) now, whatever its Download
// setting.
void UpdateComponentsNow(Row row);

}  // namespace browser_traffic

#endif  // CHROME_BROWSER_BROWSER_TRAFFIC_BROWSER_TRAFFIC_MONITOR_H_
