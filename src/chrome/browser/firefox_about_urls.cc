// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/firefox_about_urls.h"

#include <string_view>

#include "base/containers/fixed_flat_map.h"
#include "chrome/common/webui_url_constants.h"
#include "content/public/common/url_constants.h"
#include "url/gurl.h"

void RewriteFirefoxAboutURL(GURL* url) {
  static constexpr auto kFirefoxHosts =
      base::MakeFixedFlatMap<std::string_view, std::string_view>({
          {"addons", chrome::kChromeUIExtensionsHost},
          {"certificate", "certificate-manager"},
          {"debugging", "inspect"},
          {"home", chrome::kChromeUINewTabHost},
          {"license", chrome::kChromeUICreditsHost},
          {"logins", "password-manager"},
          {"networking", "net-internals"},
          {"policies", chrome::kChromeUIPolicyHost},
          {"preferences", chrome::kChromeUISettingsHost},
          {"serviceworkers", "serviceworker-internals"},
          {"support", chrome::kChromeUIVersionHost},
          {"webrtc", "webrtc-internals"},
      });
  if (!url->SchemeIs(content::kChromeUIScheme)) {
    return;
  }
  auto firefox = kFirefoxHosts.find(url->GetHost());
  if (firefox != kFirefoxHosts.end()) {
    GURL::Replacements replacements;
    replacements.SetHostStr(firefox->second);
    *url = url->ReplaceComponents(replacements);
  }
}
