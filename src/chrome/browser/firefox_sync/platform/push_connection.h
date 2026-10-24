// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_FIREFOX_SYNC_PLATFORM_PUSH_CONNECTION_H_
#define CHROME_BROWSER_FIREFOX_SYNC_PLATFORM_PUSH_CONNECTION_H_

#include <string>
#include <string_view>

#include "base/functional/callback.h"
#include "base/memory/raw_ptr.h"
#include "base/time/time.h"
#include "base/timer/timer.h"
#include "base/values.h"
#include "mojo/public/cpp/bindings/receiver.h"
#include "mojo/public/cpp/bindings/remote.h"
#include "mojo/public/cpp/system/data_pipe.h"
#include "mojo/public/cpp/system/simple_watcher.h"
#include "services/network/public/mojom/websocket.mojom.h"

class Profile;

namespace firefox_sync {

// The connection to Mozilla's push server that Firefox desktop keeps too
// (autopush's WebSocket protocol). It registers one channel, whose endpoint
// the Mozilla account pushes a notice to whenever another device sends a tab
// or a close request. The browser's identity on the push server (its UAID),
// the channel and its endpoint are kept in profile prefs, so the endpoint
// stays the same across restarts. While it exists, it reconnects after a
// drop, waiting longer after each failed attempt.
class PushConnection : public network::mojom::WebSocketHandshakeClient,
                       public network::mojom::WebSocketClient {
 public:
  // `on_endpoint` gets the channel's endpoint once connected, `on_notice`
  // each notice for it.
  PushConnection(Profile* profile,
                 base::RepeatingCallback<void(const std::string&)> on_endpoint,
                 base::RepeatingClosure on_notice);
  PushConnection(const PushConnection&) = delete;
  PushConnection& operator=(const PushConnection&) = delete;
  ~PushConnection() override;

 private:
  void Connect();
  void Disconnect();
  // Drops the connection and tries again later.
  void Reconnect();
  void SendText(std::string_view text);
  void OnReadable(MojoResult result, const mojo::HandleSignalsState& state);
  void OnMessage(const std::string& text);
  void OnHello(const base::DictValue& message);
  void Ping();

  // network::mojom::WebSocketHandshakeClient:
  void OnOpeningHandshakeStarted(
      network::mojom::WebSocketHandshakeRequestPtr request) override;
  void OnFailure(const std::string& message,
                 int net_error,
                 int response_code) override;
  void OnConnectionEstablished(
      mojo::PendingRemote<network::mojom::WebSocket> socket,
      mojo::PendingReceiver<network::mojom::WebSocketClient> client_receiver,
      network::mojom::WebSocketHandshakeResponsePtr response,
      mojo::ScopedDataPipeConsumerHandle readable,
      mojo::ScopedDataPipeProducerHandle writable) override;

  // network::mojom::WebSocketClient:
  void OnDataFrame(bool finish,
                   network::mojom::WebSocketMessageType type,
                   uint64_t data_len) override;
  void OnDropChannel(bool was_clean,
                     uint16_t code,
                     const std::string& reason) override;
  void OnClosingHandshake() override;

  const raw_ptr<Profile> profile_;
  base::RepeatingCallback<void(const std::string&)> on_endpoint_;
  base::RepeatingClosure on_notice_;

  mojo::Receiver<network::mojom::WebSocketHandshakeClient> handshake_{this};
  mojo::Receiver<network::mojom::WebSocketClient> client_{this};
  mojo::Remote<network::mojom::WebSocket> socket_;
  mojo::ScopedDataPipeConsumerHandle readable_;
  mojo::ScopedDataPipeProducerHandle writable_;
  mojo::SimpleWatcher readable_watcher_;
  // The message being read, and the bytes of its frames still to read.
  std::string message_;
  uint64_t to_read_ = 0;
  bool message_finished_ = false;

  base::TimeDelta backoff_;
  base::OneShotTimer reconnect_;
  base::RepeatingTimer ping_;
};

}  // namespace firefox_sync

#endif  // CHROME_BROWSER_FIREFOX_SYNC_PLATFORM_PUSH_CONNECTION_H_
