// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/content_settings/autoplay_setting.h"

#include "components/content_settings/core/browser/host_content_settings_map.h"
#include "content/public/browser/navigation_handle.h"
#include "content/public/browser/render_frame_host.h"
#include "mojo/public/cpp/bindings/associated_remote.h"
#include "third_party/blink/public/common/associated_interfaces/associated_interface_provider.h"
#include "third_party/blink/public/mojom/autoplay/autoplay.mojom.h"
#include "url/gurl.h"
#include "url/origin.h"

namespace autoplay_setting {

void ReadyToCommitNavigation(HostContentSettingsMap& map,
                             const GURL& top_url,
                             content::NavigationHandle& navigation) {
  int32_t flags;
  switch (map.GetContentSetting(top_url, top_url,
                                ContentSettingsType::AUTOPLAY)) {
    case CONTENT_SETTING_ALLOW:
      flags = blink::mojom::kAutoplayFlagForceAllow;
      break;
    case CONTENT_SETTING_BLOCK:
      flags = blink::mojom::kAutoplayFlagDocumentInputRequired;
      break;
    default:
      return;
  }
  // The renderer applies flags whose origin is the committed document's.
  url::Origin origin = navigation.GetOriginToCommit().value_or(
      url::Origin::Create(navigation.GetURL()));
  mojo::AssociatedRemote<blink::mojom::AutoplayConfigurationClient> client;
  navigation.GetRenderFrameHost()->GetRemoteAssociatedInterfaces()->GetInterface(
      &client);
  client->AddAutoplayFlags(origin, flags);
}

}  // namespace autoplay_setting
