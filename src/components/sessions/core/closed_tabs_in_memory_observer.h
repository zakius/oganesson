// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef COMPONENTS_SESSIONS_CORE_CLOSED_TABS_IN_MEMORY_OBSERVER_H_
#define COMPONENTS_SESSIONS_CORE_CLOSED_TABS_IN_MEMORY_OBSERVER_H_

#include "base/functional/bind.h"
#include "components/prefs/pref_change_registrar.h"
#include "components/sessions/core/closed_tabs_in_memory.h"
#include "components/sessions/core/tab_restore_service.h"
#include "components/sessions/core/tab_restore_service_observer.h"

namespace sessions {

// Empties a TabRestoreService as soon as it holds closed windows, groups or
// splits that aren't to be kept (history isn't saved, nor kept in memory),
// and when keeping them in memory is turned off. Closed tabs never get in:
// TabRestoreServiceImpl::CreateHistoricalTab drops them first. Owns itself
// and goes away with the service.
class ClosedTabsInMemoryObserver : public TabRestoreServiceObserver {
 public:
  static void Attach(TabRestoreService* service, PrefService* prefs) {
    new ClosedTabsInMemoryObserver(service, prefs);
  }

  ClosedTabsInMemoryObserver(const ClosedTabsInMemoryObserver&) = delete;
  ClosedTabsInMemoryObserver& operator=(const ClosedTabsInMemoryObserver&) =
      delete;

  // The service's observer list allows reentrancy: ClearEntries() notifies
  // again, and finds nothing left to clear.
  void TabRestoreServiceChanged(TabRestoreService* service) override {
    if (!KeepsClosedTabs(*registrar_.prefs()) && !service->entries().empty()) {
      service->ClearEntries();
    }
  }

  void TabRestoreServiceDestroyed(TabRestoreService* service) override {
    service->RemoveObserver(this);
    delete this;
  }

 private:
  ClosedTabsInMemoryObserver(TabRestoreService* service, PrefService* prefs) {
    service->AddObserver(this);
    registrar_.Init(prefs);
    registrar_.Add(
        kKeepClosedTabsInMemory,
        base::BindRepeating(
            &ClosedTabsInMemoryObserver::TabRestoreServiceChanged,
            base::Unretained(this), base::Unretained(service)));
  }
  ~ClosedTabsInMemoryObserver() override = default;

  PrefChangeRegistrar registrar_;
};

}  // namespace sessions

#endif  // COMPONENTS_SESSIONS_CORE_CLOSED_TABS_IN_MEMORY_OBSERVER_H_
