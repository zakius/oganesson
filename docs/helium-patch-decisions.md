# Helium patch decisions

oganesson carries Helium's whole series (`helium/patches/series`) as it is, in the `helium` submodule, and never edits it. What it doesn't want of Helium is handled in one of two ways:

- **Dropped**, in `patches/helium-drops.txt` with the reason, which `oganesson.py` removes from the series. Only for a patch that no later Helium patch builds on: `./oganesson.py check-patches` fails otherwise.
- **Carried and turned off** by our patches, for an unwanted patch that later ones build on. The table below says how.

Every other Helium patch is carried, also the ones earlier reviews called indifferent. A new Helium release's patches are carried unless they go into the drop list; `tools/update_helium.py` lists them. Until 2026-10-14 oganesson carried a hand-picked subset of 139 patches, which needed 21 of Helium's patches edited to apply; that is why the earlier lists named patches "omitted".

## Decisions that are not per patch

- Firefox-style tab placement and selection after closing a tab is a must have, with selectable alternatives: Settings > Behavior > Tab behavior, a Chromium or Firefox preset over knobs, Helium's "next to the active tab" switch among them ([tab behavior](tab-behavior.md)).
- Helium's visual redesign patches (`helium/ui/*`, `helium/ui/layout/*`, `helium/settings/*`) are carried. We may want our own design later.
- Memory Saver, infinite tab freezing and Back-to-opener stay off by default. The settings stay available; their default-on patches are dropped.
- No Helium servers by default. Helium's services are off (`oganesson/core/no-helium-services`), and with them component updates, uBlock asset downloads, spellcheck dictionary downloads and the extension download proxy. The user can turn them on in Settings.
- uBlock Origin: Helium's patch set. With Helium's services off, filter lists update from uBlock's own URLs (dubna's `ublock-assets-update`). Revisit if the WebExtensions uBlock Origin becomes reliable.
- Extension installs from the Chrome Web Store and AMO stay supported. Helium's download proxy (`proxy-extension-downloads`) acts only with its services on.
- Firefox Sync replaces Helium's sync. Its patches (`helium/core/sync/*`) are carried, as later patches build on them, and stay inert: Helium sync needs Helium's services and its provider feature is off.
- Onboarding (`helium/core/onboarding-page`) is carried but never shown: a first run opens a normal window. It may serve as the basis of our own.
- Password manager stays enabled, so `hop/disable-password-manager` is dropped.
- The `ungoogled-chromium/add-flag-*` patches are carried.
- A patch that only changes the default of an existing Chromium setting is dropped when we don't want that default. A patch that adds a new setting or flag is kept. Many `add-flag-*` patches add only a `chrome://flags` entry, not a Settings page option.
- Credits and licensing: credit every project we take patches from and handle their licenses correctly. Keep `add-credits`, and adapt `helium/ui/licenses-in-credits` and `helium/core/update-credits` to our credits page.
- Importers: keep all, including Helium's Zen and Arc importers.
- `enable-tab-hover-cards` is dropped, since hover-card images are already on by default outside Mac. The ungoogled `add-flag-for-tab-hover-cards` flag (None or Tooltip) is kept.
- `inox-patchset/modify-default-prefs` is kept. Its list of defaults still needs an audit.
- `ungoogled-chromium/disable-webstore-urls` is kept. Check at build time that Chrome Web Store installs still work.
- Fingerprint noise (`helium/core/noise/*` and its settings page) is carried and off by default; its page-info UI is dropped.

## Carried and turned off

| Patches | How |
|---|---|
| `helium/core/services-prefs`, `services-schema-nag`, `component-updates`, `fixups-component-setup`, `proxy-extension-downloads`, `reenable-spellcheck-downloads`, `ublock-helium-services` | Helium's services are off by default (`oganesson/core/no-helium-services`), and these act only with them. uBlock Origin's filter lists update from uBlock's own URLs (dubna's `ublock-assets-update`). Spellcheck dictionaries download only with the services on. |
| `helium/core/add-native-bangs` | Off by default: the bang list comes from Helium's services. On again once we have our own bang source. |
| `helium/core/reenable-update-checks`, `add-updater-preference`, `add-update-channel-flag`, `add-helium-versioning` | Helium's update checks are off by default: oganesson updates from its package repository. |
| `helium/core/onboarding-page` | Marked as done by default: never shown. |
| `helium/core/crash-reporting-prefs`, `helium/settings/crash-reporting-settings` | Crash reporting is off by default: reports would go to Helium's crash server. |
| `helium/core/noise/*`, `helium/settings/helium-noise-settings` | Off by default; the setting stays. |
| `helium/core/sync/*` | Inert: needs Helium's services, and its provider feature is off. |
| `helium/hop/setup` | Inert: the one policy Helium ships with it (`hop/disable-password-manager`) is dropped. |
| `helium/core/override-chrome-protocol` | Internal pages show as `oganesson://` instead of `helium://` (`late/branding`); `chrome://` still works. |
| `helium/core/change-chromium-branding` | `late/branding` renames Helium to oganesson. |
| `helium/core/flags-setup`, `add-low-power-framerate-flag`, `bookmark-open-all-confirmation-flag`, `helium/ui/hide-page-actions-flag`, the `ungoogled-chromium/add-flag-*` and `bromite/*-flags` patches | Only add `chrome://flags` entries, off by default. |
| `helium/core/search/restore-google`, `force-eu-search-features`, `break-favicons`, `update-default-browser-prefs`, `add-default-browser-reject-button`, `remove-dead-toolbar-actions`, `scan-chrome-native-messaging-hosts` | Neutral as they are. |

## Notes on carried patches

- `helium/core/ridiculous-google-compat-exceptions` (Helium 0.19.2): keeps Google sign-in, session cookies and security-key enrollment working under domain substitution. Maintainer's decision, 2026-10-09.
- `upstream-fixes/tab-restore-live-tabs` (Helium 0.19.1): kept, vendored before `helium/core/lazy-session-restore`. Maintainer's decision, 2026-10-08.
- `helium/core/disable-annoying-infobars` (Helium 0.19.1): kept; its kPdfInfoBar change covers `helium/core/disable-pdf-infobar`. Maintainer's decision, 2026-10-08.
- `helium/core/prioritize-platform-policy-loading` (Helium 0.18.2): uBlock Origin reads its managed settings at startup in milliseconds, not seconds. Maintainer's decision, 2026-10-02.
- `helium/ui/tab-search-in-toolbar`: tab search is a toolbar button, as Firefox's "List all tabs" is, and its bubble opens under it. Maintainer's decision, 2026-10-04.
- `helium/core/mute-tab-context-menu` (Helium 0.18.3, #2631): Mute tab / Unmute tab in the tab context menu, as Firefox's "Mute Tab". Maintainer's decision, 2026-10-06.
- `helium/settings/disable-safety-hub-page`: Safety Hub reports on services this build doesn't have (Safe Browsing, password leak check, updates). Maintainer reported it, 2026-10-06.
- `helium/settings/remove-safety-hub-entry-points`: same reason; removes the settings entry points to Safety Hub. Maintainer reported it, 2026-10-06. The app menu's Safety Hub notification lives in the omitted `helium/ui/app-menu-model`, so `oganesson/ui/no-safety-hub-menu` drops it alone.
- `helium/core/open-new-tabs-next-to-active-tab-option`: kept for its pref and switch, one of Tab behavior's knobs: Firefox's `browser.tabs.insertAfterCurrent`. Turned on, it leaves the Chromium preset, so Firefox's rules place the tab and the patch's own placement in `AddTab` no longer runs; the patch stays whole to stay comparable with upstream.
- `ungoogled-chromium/add-flag-to-close-window-with-last-tab`: Firefox's `browser.tabs.closeWindowWithLastTab`. Maintainer's decision, 2026-10-11.
- `helium/core/close-tabs-to-left`: "Close tabs to the left", as in Firefox's tab menu. Maintainer's decision, 2026-10-11.
- `helium/core/hibernate-tab-context-menu`: unloads a tab from the tab menu, as Firefox's "Unload Tab"; Memory Saver stays off by default. Maintainer's decision, 2026-10-11.
- `helium/core/network/global-privacy-control-pref`: a Global Privacy Control setting, as in Firefox. Maintainer's decision, 2026-10-11.
- `helium/core/network/disable-ech-flag`: adds a flag only. Maintainer's decision, 2026-10-11.
- `helium/core/network/quic-v2-flag`: adds a flag only. Maintainer's decision, 2026-10-11.
- `helium/core/network/split-clienthello`: adds a flag only. Maintainer's decision, 2026-10-11.
- `helium/core/network/ignore-system-proxy-server-flag`: adds a flag only. Maintainer's decision, 2026-10-11.
- `helium/ui/show-tabs-from-non-account-backends`: History's "Tabs from other devices" shows Firefox Sync's open tabs without a Google sign-in (`oganesson/core/firefox-sync-remote-tabs`). Maintainer's decision, 2026-10-11.

## Taken from ungoogled-chromium, not in Helium (1)

Ours, in `patches/series`; `tools/update_helium.py` doesn't track them, so refresh them from ungoogled-chromium by hand.

- `ungoogled-chromium/keep-expired-flags` (ungoogled-chromium `ffeb45a`): expired `chrome://flags` entries stay usable. Helium replaced it with `exclude-irrelevant-flags`, which we drop. Maintainer's decision, 2026-10-11.
