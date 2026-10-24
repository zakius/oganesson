// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/firefox_sync/platform/push_connection.h"

#include <algorithm>
#include <optional>
#include <utility>
#include <vector>

#include "base/containers/span.h"
#include "base/environment.h"
#include "base/functional/bind.h"
#include "base/functional/callback_helpers.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/logging.h"
#include "base/uuid.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/common/oganesson_pref_names.h"
#include "components/prefs/pref_service.h"
#include "content/public/browser/storage_partition.h"
#include "net/base/isolation_info.h"
#include "net/storage_access_api/status.h"
#include "net/traffic_annotation/network_traffic_annotation.h"
#include "services/network/public/cpp/constants.h"
#include "services/network/public/mojom/ip_address_space.mojom.h"
#include "services/network/public/mojom/network_context.mojom.h"
#include "url/gurl.h"
#include "url/origin.h"

namespace firefox_sync {

namespace {

constexpr char kPushServer[] = "wss://push.services.mozilla.com/";
// As Firefox desktop: the server drops a connection that says nothing for
// longer.
constexpr base::TimeDelta kPingInterval = base::Minutes(30);
constexpr base::TimeDelta kFirstRetry = base::Seconds(30);
constexpr base::TimeDelta kLastRetry = base::Minutes(30);
// Push server messages are small JSON; a notice carries at most 4 kB.
constexpr size_t kMaxMessageSize = 64 * 1024;

constexpr net::NetworkTrafficAnnotationTag kTrafficAnnotation =
    net::DefineNetworkTrafficAnnotation("oganesson_firefox_sync_push", R"(
      semantics {
        sender: "Firefox Sync"
        description:
          "Keeps a connection to Mozilla's push server, as Firefox does, so "
          "tabs the user's other devices send arrive at once."
        trigger: "Signed in to Firefox Sync, with Receive tabs instantly on."
        data: "The browser's push server identity and channel, and "
              "acknowledgements of the notices it receives."
        destination: OTHER
      }
      policy {
        cookies_allowed: NO
        setting: "Settings, Sync: Receive tabs instantly."
        policy_exception_justification: "Not implemented."
      })");

GURL ServerUrl() {
  // A test's own push server (tools/fake_firefox_sync.py).
  std::optional<std::string> url =
      base::Environment::Create()->GetVar("OGANESSON_PUSH_SERVER");
  return GURL(url && !url->empty() ? *url : kPushServer);
}

std::string ToJson(const base::DictValue& message) {
  return base::WriteJson(message).value_or("{}");
}

}  // namespace

PushConnection::PushConnection(
    Profile* profile,
    base::RepeatingCallback<void(const std::string&)> on_endpoint,
    base::RepeatingClosure on_notice)
    : profile_(profile),
      on_endpoint_(std::move(on_endpoint)),
      on_notice_(std::move(on_notice)),
      readable_watcher_(FROM_HERE, mojo::SimpleWatcher::ArmingPolicy::MANUAL),
      backoff_(kFirstRetry) {
  Connect();
}

PushConnection::~PushConnection() = default;

void PushConnection::Connect() {
  const GURL url = ServerUrl();
  const url::Origin origin = url::Origin::Create(url);
  auto handshake = handshake_.BindNewPipeAndPassRemote();
  handshake_.set_disconnect_handler(
      base::BindOnce(&PushConnection::Reconnect, base::Unretained(this)));
  profile_->GetDefaultStoragePartition()->GetNetworkContext()->CreateWebSocket(
      url, /*requested_protocols=*/{}, net::StorageAccessApiStatus::kNone,
      net::IsolationInfo::CreateForInternalRequest(origin),
      /*additional_headers=*/{}, network::OriginatingProcessId::browser(),
      origin, network::mojom::ClientSecurityState::New(),
      network::mojom::kWebSocketOptionBlockAllCookies,
      net::MutableNetworkTrafficAnnotationTag(kTrafficAnnotation),
      std::move(handshake),
      /*url_loader_network_observer=*/mojo::NullRemote(),
      /*auth_handler=*/mojo::NullRemote(),
      /*header_client=*/mojo::NullRemote(),
      /*throttling_profile_id=*/std::nullopt,
      network::GetNoOpNetworkRestrictionsId(),
      /*target_address_space=*/network::mojom::IPAddressSpace::kUnknown,
      /*target_network=*/std::nullopt);
}

void PushConnection::Disconnect() {
  ping_.Stop();
  readable_watcher_.Cancel();
  socket_.reset();
  client_.reset();
  handshake_.reset();
  readable_.reset();
  writable_.reset();
  message_.clear();
  to_read_ = 0;
  message_finished_ = false;
}

void PushConnection::Reconnect() {
  Disconnect();
  reconnect_.Start(FROM_HERE, backoff_,
                   base::BindOnce(&PushConnection::Connect,
                                  base::Unretained(this)));
  backoff_ = std::min(backoff_ * 2, kLastRetry);
}

void PushConnection::SendText(std::string_view text) {
  if (!socket_ || !writable_) {
    return;
  }
  socket_->SendMessage(network::mojom::WebSocketMessageType::TEXT,
                       text.size());
  if (writable_->WriteAllData(base::as_byte_span(text)) != MOJO_RESULT_OK) {
    Reconnect();
  }
}

void PushConnection::OnOpeningHandshakeStarted(
    network::mojom::WebSocketHandshakeRequestPtr request) {}

void PushConnection::OnFailure(const std::string& message,
                               int net_error,
                               int response_code) {
  VLOG(1) << "Firefox Sync push: " << message;
  Reconnect();
}

void PushConnection::OnConnectionEstablished(
    mojo::PendingRemote<network::mojom::WebSocket> socket,
    mojo::PendingReceiver<network::mojom::WebSocketClient> client_receiver,
    network::mojom::WebSocketHandshakeResponsePtr response,
    mojo::ScopedDataPipeConsumerHandle readable,
    mojo::ScopedDataPipeProducerHandle writable) {
  socket_.Bind(std::move(socket));
  readable_ = std::move(readable);
  writable_ = std::move(writable);
  readable_watcher_.Watch(
      readable_.get(), MOJO_HANDLE_SIGNAL_READABLE,
      MOJO_TRIGGER_CONDITION_SIGNALS_SATISFIED,
      base::BindRepeating(&PushConnection::OnReadable, base::Unretained(this)));
  client_.Bind(std::move(client_receiver));
  // The handshake pipe closes now; the client pipe catches a network
  // service crash from here on.
  handshake_.set_disconnect_handler(base::DoNothing());
  client_.set_disconnect_handler(
      base::BindOnce(&PushConnection::Reconnect, base::Unretained(this)));
  socket_->StartReceiving();

  PrefService* prefs = profile_->GetPrefs();
  base::DictValue hello;
  hello.Set("messageType", "hello");
  // Without one, the server gives the browser a new identity.
  if (const std::string& uaid = prefs->GetString(prefs::kFirefoxSyncPushUaid);
      !uaid.empty()) {
    hello.Set("uaid", uaid);
  }
  hello.Set("use_webpush", true);
  const std::string& channel = prefs->GetString(prefs::kFirefoxSyncPushChannel);
  if (!channel.empty()) {
    hello.Set("channelIDs", base::ListValue().Append(channel));
  }
  hello.Set("broadcasts", base::DictValue());
  SendText(ToJson(hello));
}

void PushConnection::OnDataFrame(bool finish,
                                 network::mojom::WebSocketMessageType type,
                                 uint64_t data_len) {
  if (message_.size() + data_len > kMaxMessageSize) {
    Reconnect();
    return;
  }
  to_read_ = data_len;
  message_finished_ = finish;
  // Frames come one after another: the next waits until this one is read.
  client_.Pause();
  OnReadable(MOJO_RESULT_OK, mojo::HandleSignalsState());
}

void PushConnection::OnReadable(MojoResult, const mojo::HandleSignalsState&) {
  while (to_read_ > 0) {
    std::vector<uint8_t> buffer(to_read_);
    size_t read = 0;
    MojoResult result =
        readable_->ReadData(MOJO_READ_DATA_FLAG_NONE, buffer, read);
    if (result == MOJO_RESULT_SHOULD_WAIT) {
      readable_watcher_.ArmOrNotify();
      return;
    }
    if (result != MOJO_RESULT_OK) {
      Reconnect();
      return;
    }
    message_.append(buffer.begin(), buffer.begin() + read);
    to_read_ -= read;
  }
  client_.Resume();
  if (message_finished_) {
    std::string text = std::move(message_);
    message_.clear();
    message_finished_ = false;
    OnMessage(text);
  }
}

void PushConnection::OnMessage(const std::string& text) {
  std::optional<base::DictValue> message =
      base::JSONReader::ReadDict(text, base::JSON_PARSE_CHROMIUM_EXTENSIONS);
  const std::string* type = message ? message->FindString("messageType")
                                    : nullptr;
  if (!type) {
    // "{}": the server's answer to a ping.
    return;
  }
  PrefService* prefs = profile_->GetPrefs();
  const std::string* channel = message->FindString("channelID");
  if (*type == "hello") {
    OnHello(*message);
  } else if (*type == "register") {
    const std::string* endpoint = message->FindString("pushEndpoint");
    if (message->FindInt("status") == 200 && endpoint && channel &&
        *channel == prefs->GetString(prefs::kFirefoxSyncPushChannel)) {
      prefs->SetString(prefs::kFirefoxSyncPushEndpoint, *endpoint);
      on_endpoint_.Run(*endpoint);
    }
  } else if (*type == "notification" && channel) {
    // Acknowledged, or the server sends it again on every connect.
    const std::string* version = message->FindString("version");
    base::DictValue update;
    update.Set("channelID", *channel);
    update.Set("version", version ? *version : std::string());
    base::DictValue ack;
    ack.Set("messageType", "ack");
    ack.Set("updates", base::ListValue().Append(std::move(update)));
    SendText(ToJson(ack));
    if (*channel == prefs->GetString(prefs::kFirefoxSyncPushChannel)) {
      on_notice_.Run();
    }
  }
}

void PushConnection::OnHello(const base::DictValue& message) {
  const std::string* uaid = message.FindString("uaid");
  if (message.FindInt("status") != 200 || !uaid) {
    Reconnect();
    return;
  }
  backoff_ = kFirstRetry;
  ping_.Start(FROM_HERE, kPingInterval,
              base::BindRepeating(&PushConnection::Ping,
                                  base::Unretained(this)));
  PrefService* prefs = profile_->GetPrefs();
  // A new identity, such as on the first connection or after the server
  // forgot the old one, has no channels yet.
  if (*uaid != prefs->GetString(prefs::kFirefoxSyncPushUaid)) {
    prefs->SetString(prefs::kFirefoxSyncPushUaid, *uaid);
    prefs->ClearPref(prefs::kFirefoxSyncPushChannel);
    prefs->ClearPref(prefs::kFirefoxSyncPushEndpoint);
  }
  const std::string& endpoint =
      prefs->GetString(prefs::kFirefoxSyncPushEndpoint);
  if (!endpoint.empty()) {
    on_endpoint_.Run(endpoint);
    return;
  }
  const std::string channel =
      base::Uuid::GenerateRandomV4().AsLowercaseString();
  prefs->SetString(prefs::kFirefoxSyncPushChannel, channel);
  base::DictValue reg;
  reg.Set("messageType", "register");
  reg.Set("channelID", channel);
  SendText(ToJson(reg));
}

void PushConnection::Ping() {
  SendText("{}");
}

void PushConnection::OnDropChannel(bool was_clean,
                                   uint16_t code,
                                   const std::string& reason) {
  VLOG(1) << "Firefox Sync push: dropped, " << code << " " << reason;
  Reconnect();
}

void PushConnection::OnClosingHandshake() {}

}  // namespace firefox_sync
