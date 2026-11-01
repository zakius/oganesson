// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/browser_traffic/browser_traffic_monitor.h"

#include <algorithm>
#include <memory>
#include <utility>
#include <vector>

#include "base/barrier_callback.h"
#include "base/functional/bind.h"
#include "base/functional/callback.h"
#include "base/functional/callback_helpers.h"
#include "base/no_destructor.h"
#include "base/scoped_observation.h"
#include "base/time/time.h"
#include "base/timer/timer.h"
#include "build/build_config.h"
#include "chrome/browser/browser_process.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/profiles/profile_manager.h"
#include "chrome/browser/profiles/profile_manager_observer.h"
#include "components/component_updater/component_updater_service.h"
#include "components/helium_services/pref_names.h"
#include "components/prefs/pref_change_registrar.h"
#include "components/prefs/pref_service.h"
#include "components/update_client/crx_update_item.h"
#include "components/update_client/update_client_errors.h"
#include "net/base/load_flags.h"
#include "net/http/http_response_headers.h"
#include "net/traffic_annotation/network_traffic_annotation.h"
#include "services/network/public/cpp/resource_request.h"
#include "services/network/public/cpp/shared_url_loader_factory.h"
#include "services/network/public/cpp/simple_url_loader.h"
#include "url/gurl.h"

#if BUILDFLAG(IS_WIN)
#include "chrome/install_static/install_util.h"
#endif

namespace browser_traffic {

namespace {

constexpr base::TimeDelta kHealthCheckInterval = base::Hours(1);
constexpr base::TimeDelta kHealthCheckTimeout = base::Seconds(15);

constexpr net::NetworkTrafficAnnotationTag kHealthCheckAnnotation =
    net::DefineNetworkTrafficAnnotation("browser_traffic_health_check", R"(
        semantics {
          sender: "Browser traffic"
          description:
            "Checks that the user's own helium-services server answers, so "
            "Settings can show whether downloads through it work."
          trigger:
            "Once an hour while a row of Settings > Browser traffic goes "
            "through the server and the health check is periodic, and when "
            "the user tests the server."
          data: "None."
          destination: OTHER
          destination_other: "The server the user set."
        }
        policy {
          cookies_allowed: NO
          setting:
            "Settings > Browser traffic: the health check, or no row set to "
            "Proxy."
          policy_exception_justification: "Not implemented."
        })");

PrefService& LocalState() {
  return *g_browser_process->local_state();
}

// Helium's profile code reads browser traffic through helium_services, and
// its pref observers watch helium.services.* in each profile. Those prefs
// are derived: a settings change bumps the schema version, which every
// observer watches, and the absence of stale certificate data is in
// disable_schema_alerts, which the app menu icon watches.
class Monitor : public component_updater::ServiceObserver,
                public ProfileManagerObserver {
 public:
  Monitor() {
    registrar_.Init(&LocalState());
    browser_traffic::AddObserver(registrar_,
                base::BindRepeating(&Monitor::OnSettingsChanged,
                                    base::Unretained(this)),
                base::BindRepeating(&Monitor::OnResultsChanged,
                                    base::Unretained(this)));
    if (auto* updater = g_browser_process->component_updater()) {
      updater_observation_.Observe(updater);
    }
    if (auto* manager = g_browser_process->profile_manager()) {
      profiles_observation_.Observe(manager);
    }
    Reschedule();
    OnResultsChanged();
  }

  // component_updater::ServiceObserver:
  void OnEvent(const update_client::CrxUpdateItem& item) override {
    const std::optional<Row> row = RowForComponent(item.id);
    if (!row) {
      return;
    }
    bool fetched;
    switch (item.state) {
      case update_client::ComponentState::kUpToDate:
      case update_client::ComponentState::kUpdated:
        fetched = true;
        break;
      case update_client::ComponentState::kUpdateError:
        fetched = false;
        break;
      default:
        return;
    }
    const base::Time now = base::Time::Now();
    if (fetched && *row == Row::kCertificates) {
      RecordCertificatesUpdated(LocalState(), now);
    }
    if (GetProxyURL(LocalState(), *row, "com")) {
      RecordServerResult(LocalState(), fetched, now);
    }
  }

  // ProfileManagerObserver:
  void OnProfileAdded(Profile* profile) override { SetNoStaleData(profile); }
  void OnProfileManagerDestroying() override {
    profiles_observation_.Reset();
  }

 private:
  void OnSettingsChanged() {
    for (Profile* profile : LoadedProfiles()) {
      PrefService* prefs = profile->GetPrefs();
      prefs->SetInteger(prefs::kHeliumSchemaVersion,
                        prefs->GetInteger(prefs::kHeliumSchemaVersion) + 1);
    }
    Reschedule();
    OnResultsChanged();
  }

  void OnResultsChanged() {
    for (Profile* profile : LoadedProfiles()) {
      SetNoStaleData(profile);
    }
    stale_timer_.Stop();
    const base::Time now = base::Time::Now();
    if (std::optional<base::Time> stale_at =
            CertificatesStaleAt(LocalState(), now)) {
      stale_timer_.Start(FROM_HERE, *stale_at - now + base::Seconds(1), this,
                         &Monitor::OnResultsChanged);
    }
  }

  void SetNoStaleData(Profile* profile) {
    profile->GetPrefs()->SetBoolean(
        prefs::kHeliumDisableSchemaAlerts,
        !CertificatesStale(LocalState(), base::Time::Now()));
  }

  void Reschedule() {
    const bool periodic =
        GetHealthCheck(LocalState()) == HealthCheck::kPeriodically &&
        NeedsServer(LocalState(), ShownRows()) && GetServer(LocalState());
    if (!periodic) {
      health_timer_.Stop();
    } else if (!health_timer_.IsRunning()) {
      health_timer_.Start(FROM_HERE, kHealthCheckInterval, this,
                          &Monitor::CheckHealth);
    }
  }

  void CheckHealth() {
    if (std::optional<GURL> server = GetServer(LocalState())) {
      CheckServer(*server, base::DoNothing());
    }
  }

  static std::vector<Profile*> LoadedProfiles() {
    ProfileManager* manager = g_browser_process->profile_manager();
    return manager ? manager->GetLoadedProfiles() : std::vector<Profile*>();
  }

  PrefChangeRegistrar registrar_;
  base::RepeatingTimer health_timer_;
  base::OneShotTimer stale_timer_;
  base::ScopedObservation<component_updater::ComponentUpdateService,
                          component_updater::ServiceObserver>
      updater_observation_{this};
  base::ScopedObservation<ProfileManager, ProfileManagerObserver>
      profiles_observation_{this};
};

std::unique_ptr<Monitor>& TheMonitor() {
  static base::NoDestructor<std::unique_ptr<Monitor>> monitor;
  return *monitor;
}

void OnServerChecked(std::unique_ptr<network::SimpleURLLoader> loader,
                     const GURL& server,
                     base::OnceCallback<void(bool)> callback,
                     scoped_refptr<net::HttpResponseHeaders> headers) {
  const bool answered = headers && headers->response_code() == 204;
  if (g_browser_process->local_state() && GetServer(LocalState()) == server) {
    RecordServerResult(LocalState(), answered, base::Time::Now());
  }
  std::move(callback).Run(answered);
}

}  // namespace

BrowserUpdates GetBrowserUpdates() {
#if BUILDFLAG(IS_WIN)
  return install_static::IsSystemInstall() ? BrowserUpdates::kManaged
                                           : BrowserUpdates::kRow;
#else
  return BrowserUpdates::kPackageManager;
#endif
}

std::vector<Row> ShownRows() {
  std::vector<Row> rows;
  for (Row row : kAllRows) {
    if (row != Row::kBrowserUpdates ||
        GetBrowserUpdates() == BrowserUpdates::kRow) {
      rows.push_back(row);
    }
  }
  return rows;
}

void StartMonitor() {
  TheMonitor() = std::make_unique<Monitor>();
}

void StopMonitor() {
  TheMonitor().reset();
}

void CheckServer(const GURL& server, base::OnceCallback<void(bool)> callback) {
  auto request = std::make_unique<network::ResourceRequest>();
  request->url = server.Resolve(kConnectivityCheckPath);
  request->credentials_mode = network::mojom::CredentialsMode::kOmit;
  request->load_flags = net::LOAD_BYPASS_CACHE | net::LOAD_DISABLE_CACHE;
  auto loader = network::SimpleURLLoader::Create(std::move(request),
                                                 kHealthCheckAnnotation);
  loader->SetTimeoutDuration(kHealthCheckTimeout);
  network::SimpleURLLoader* raw_loader = loader.get();
  raw_loader->DownloadHeadersOnly(
      g_browser_process->shared_url_loader_factory().get(),
      base::BindOnce(&OnServerChecked, std::move(loader), server,
                     std::move(callback)));
}

void UpdateComponentsNow(Row row) {
  UpdateComponentsNow(row, base::DoNothing());
}

void UpdateComponentsNow(Row row, base::OnceCallback<void(bool)> done) {
  auto* updater = g_browser_process->component_updater();
  const base::span<const std::string_view> ids = ComponentsOf(row);
  if (!updater || ids.empty()) {
    std::move(done).Run(false);
    return;
  }
  const auto checked = base::BarrierCallback<update_client::Error>(
      ids.size(),
      base::BindOnce(
          [](base::OnceCallback<void(bool)> done,
             std::vector<update_client::Error> errors) {
            std::move(done).Run(std::ranges::all_of(
                errors, [](update_client::Error error) {
                  return error == update_client::Error::NONE;
                }));
          },
          std::move(done)));
  for (std::string_view id : ids) {
    updater->GetOnDemandUpdater().OnDemandUpdate(
        std::string(id), component_updater::OnDemandUpdater::Priority::FOREGROUND,
        checked);
  }
}

}  // namespace browser_traffic
