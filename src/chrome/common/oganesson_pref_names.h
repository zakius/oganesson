// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_COMMON_OGANESSON_PREF_NAMES_H_
#define CHROME_COMMON_OGANESSON_PREF_NAMES_H_

namespace prefs {

// Dictionary mapping mouse gestures, such as the stroke chain "LU" or
// "wheel-up", to a browser command id or to an extension command stored as
// {"extension": id, "command": name}.
inline constexpr char kMouseGestures[] = "oganesson.mouse_gestures";

// In local state: the app icon (Settings > Appearance > App icon), by the name
// of one of oganesson_app_icon::kVariants.
inline constexpr char kAppIcon[] = "oganesson.app_icon";

// A boolean pref set to true if tabs show the icon for audio playing.
inline constexpr char kShowTabAudioIndicator[] =
    "oganesson.tabs.show_audio_indicator";
// A boolean pref set to false to hide the close buttons on tabs.
inline constexpr char kShowTabCloseButtons[] =
    "oganesson.tabs.show_close_buttons";

// Settings > Behavior > Tab behavior's knobs (docs/tab-behavior.md). Helium's
// kNewTabNextToActive, Firefox's browser.tabs.insertAfterCurrent, is the
// fifth. The defaults are the Firefox preset.
//
// Where a link opens, a TabLinkPosition.
inline constexpr char kTabLinkPosition[] = "oganesson.tabs.link_position";
enum TabLinkPosition {
  // Chromium's DetermineInsertionIndex: a foreground link right after its
  // tab, a background one after the tabs its tab opened before.
  kTabLinksChromium = 0,
  // Firefox's browser.tabs.insertRelatedAfterCurrent: after its tab and the
  // tabs it opened before.
  kTabLinksAfterRelated = 1,
  // insertRelatedAfterCurrent false: at the end.
  kTabLinksAtEnd = 2,
};
// Chromium's first choices on close: a tab the closed one opened, then one
// its opener opened. Firefox has none.
inline constexpr char kTabSelectRelatedOnClose[] =
    "oganesson.tabs.select_related_on_close";
// Firefox's browser.tabs.selectOwnerOnClose.
inline constexpr char kTabSelectOwnerOnClose[] =
    "oganesson.tabs.select_owner_on_close";
// Firefox's browser.tabs.selectMRUOnClose.
inline constexpr char kTabSelectMRUOnClose[] =
    "oganesson.tabs.select_mru_on_close";

// Firefox Sync keeps a connection to Mozilla's push server, so tabs other
// devices send arrive at once: on by default, as in Firefox.
inline constexpr char kFirefoxSyncInstantTabs[] =
    "oganesson.firefox_sync.instant_tabs";
// That connection's identity on the push server (its UAID), its channel and
// the channel's endpoint, kept so the endpoint survives restarts.
inline constexpr char kFirefoxSyncPushUaid[] = "oganesson.firefox_sync.push_uaid";
inline constexpr char kFirefoxSyncPushChannel[] =
    "oganesson.firefox_sync.push_channel";
inline constexpr char kFirefoxSyncPushEndpoint[] =
    "oganesson.firefox_sync.push_endpoint";

}  // namespace prefs

#endif  // CHROME_COMMON_OGANESSON_PREF_NAMES_H_
