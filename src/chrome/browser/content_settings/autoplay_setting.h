// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_CONTENT_SETTINGS_AUTOPLAY_SETTING_H_
#define CHROME_BROWSER_CONTENT_SETTINGS_AUTOPLAY_SETTING_H_

class GURL;
class HostContentSettingsMap;

namespace content {
class NavigationHandle;
}

// The Autoplay site setting (ContentSettingsType::AUTOPLAY), as Firefox has it:
//   ALLOW  "Allow audio and video": everything may play.
//   ASK    "Block audio": Chromium's own autoplay policy.
//   BLOCK  "Block audio and video", the default: media plays only after user
//          input in the document itself, muted media too.
// Exceptions for a site are ALLOW or BLOCK. The setting of the top-level site
// applies to all its frames.
namespace autoplay_setting {

// Before `navigation` commits a new document, tells its renderer the setting
// of `top_url` as blink autoplay flags. They apply from the first script of
// the document; a changed setting applies to the next document loaded.
void ReadyToCommitNavigation(HostContentSettingsMap& map,
                             const GURL& top_url,
                             content::NavigationHandle& navigation);

}  // namespace autoplay_setting

#endif  // CHROME_BROWSER_CONTENT_SETTINGS_AUTOPLAY_SETTING_H_
