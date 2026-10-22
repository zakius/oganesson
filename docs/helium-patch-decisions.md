# Helium patch decisions

oganesson carries Helium's whole series (`helium/patches/series`) as it is, in the `helium` submodule, and never edits it. What it doesn't want of Helium is handled in one of two ways:

- **Dropped**, in `patches/helium-drops.txt` with the reason, which `oganesson.py` removes from the series. Only for a patch that no later Helium patch builds on: `./oganesson.py check-patches` fails otherwise.
- **Carried and turned off** by my patches, for an unwanted patch that later ones build on. The table below says how.

Every other Helium patch is carried, also the ones earlier reviews called indifferent. A new Helium release's patches are carried unless they go into the drop list; `tools/update_helium.py` lists them. Until 2026-10-14 oganesson carried a hand-picked subset of 139 patches, which needed 21 of Helium's patches edited to apply; that is why the earlier lists named patches "omitted".

## Decisions that are not per patch

- Firefox-style tab placement and selection after closing a tab is a must have, and the default, with selectable alternatives: Settings > Behavior > Tab behavior, a Firefox or Chromium preset over knobs, Helium's "next to the active tab" switch among them ([tab behavior](tab-behavior.md)).
- Helium's visual redesign patches (`helium/ui/*`, `helium/ui/layout/*`, `helium/settings/*`) are carried. I may want my own design later.
- Memory Saver, infinite tab freezing and Back-to-opener stay off by default. The settings stay available; their default-on patches are dropped.
- Never Helium's own servers. What the browser downloads by itself is browser traffic (below): each kind goes direct to its source, or through the user's own helium-services server, never to Helium's host.
- uBlock Origin: Helium's patch set. Going direct, filter lists update from uBlock's own URLs (oganesson's own `oganesson/core/ublock-assets-update`). Revisit if the WebExtensions uBlock Origin becomes reliable.
- Extension installs from the Chrome Web Store are supported. Installs from AMO were taken out for now and are to come back. Helium's download proxy (`proxy-extension-downloads`) is browser traffic's Extensions row going through the user's server; going direct, store installs, updates and item data go to Google's own servers, as in Chromium. Helium itself sends them to a placeholder host without its services, so they fail.
- Firefox Sync replaces Helium's sync. Its patches (`helium/core/sync/*`) are carried, as later patches build on them, and stay inert: Helium sync needs Helium's services and its provider feature is off.
- Onboarding is my own setup (`oganesson/settings/setup-page`, `chrome://settings/setup`), with steps Welcome, Import, Firefox Sync, Browser traffic, Search, Tabs, Passwords, Privacy extras, Default browser and Done. A first start opens it. A profile that had the browser before gets it once, with only Welcome ("One new choice"), Browser traffic and Done; the Direct preset applies until the user chooses. Every step but Welcome and Browser traffic can be skipped, and Settings > About runs it again. On the Browser traffic step, Next waits for a proxied row's server to answer the test. Helium's onboarding (`helium/core/onboarding-page`) is carried but never shown, and `chrome://setup` opens mine. Decided 2026-10-21.
- Password manager stays enabled, so `helium/core/disable-password-manager` is dropped. Helium turns it off as insecure. Malware running as the user can read decrypted passwords from the browser's memory whatever the at-rest encryption, and full-disk encryption covers a stolen disk, so a separate password manager adds little. My decision, 2026-10-14.
- Its entry points stay too: `helium/ui/remove-autofill-link-to-password-manager` (the fill dropdown's Manage passwords) is dropped, `oganesson/settings/restore-autofill-page` puts back the Settings section that `helium/settings/remove-autofill` removes, and `oganesson/ui/passwords-app-menu` the app menu's Passwords and autofill submenu that `helium/ui/app-menu-model` removes. Decided 2026-10-22.
- The `ungoogled-chromium/add-flag-*` patches are carried.
- A patch that only changes the default of an existing Chromium setting is dropped when I don't want that default. A patch that adds a new setting or flag is kept. Many `add-flag-*` patches add only a `chrome://flags` entry, not a Settings page option.
- Credits and licensing: credit every project I take patches from and handle their licenses correctly. Keep `add-credits`, and adapt `helium/ui/licenses-in-credits` and `helium/core/update-credits` to my credits page.
- Importers: keep all, including Helium's Zen and Arc importers.
- `enable-tab-hover-cards` is dropped, since hover-card images are already on by default outside Mac. The ungoogled `add-flag-for-tab-hover-cards` flag (None or Tooltip) is kept.
- `inox-patchset/modify-default-prefs` is kept. Its list of defaults still needs an audit.
- `ungoogled-chromium/disable-webstore-urls` is kept. Check at build time that Chrome Web Store installs still work.
- Fingerprint noise (`helium/core/noise/*` and its settings page) is carried and off by default; its page-info UI is dropped.

## Carried and turned off

| Patches | How |
|---|---|
| `helium/core/services-prefs`, `services-schema-nag`, `component-updates`, `fixups-component-setup`, `proxy-extension-downloads`, `reenable-spellcheck-downloads`, `ublock-helium-services` | Their helpers defer to browser traffic (`oganesson/core/browser-traffic`); their prefs stay registered, derived from it. Going direct, uBlock Origin's filter lists update from uBlock's own URLs (oganesson's own `oganesson/core/ublock-assets-update`), and spellcheck dictionaries download from Google's server, as in Chromium. Helium's services page is replaced by Browser traffic. |
| `helium/core/add-native-bangs` | The bang list comes only through the user's server: without one, bangs are off. |
| `helium/core/reenable-update-checks`, `add-updater-preference`, `add-update-channel-flag`, `add-helium-versioning` | Helium's update checks are off by default: oganesson updates from its package repository. |
| `helium/core/onboarding-page` | Marked as done by default: never shown. My setup takes its place. |
| `helium/core/crash-reporting-prefs`, `helium/settings/crash-reporting-settings` | Crash reporting is off by default: reports would go to Helium's crash server. |
| `helium/core/noise/*`, `helium/settings/helium-noise-settings` | Off by default; the setting stays. |
| `helium/core/sync/*` | Inert: needs Helium's services, and its provider feature is off. |
| `helium/core/override-chrome-protocol` | Internal pages show as `oganesson://` instead of `helium://` (`late/branding`); `chrome://` still works. |
| `helium/core/change-chromium-branding` | `late/branding` renames Helium to oganesson. |
| `helium/core/flags-setup`, `add-low-power-framerate-flag`, `bookmark-open-all-confirmation-flag`, `helium/ui/hide-page-actions-flag`, the `ungoogled-chromium/add-flag-*` and `bromite/*-flags` patches | Only add `chrome://flags` entries, off by default. |
| `helium/settings/remove-autofill`, `helium/ui/app-menu-model` | `oganesson/settings/restore-autofill-page` puts back the Autofill and passwords section of Settings, and `oganesson/ui/passwords-app-menu` the app menu's Passwords and autofill submenu. `helium/settings/reorder-settings-menu` builds on the first. |
| `helium/core/update-default-browser-prefs`, `add-default-browser-reject-button`, `remove-dead-toolbar-actions`, `scan-chrome-native-messaging-hosts` | Neutral as they are. |

- Search engines: Helium's whole search group is carried, with ungoogled-chromium's `prepopulated-search-engines` (`restore-google` renames Google's engine and `engine-defaults` updates the regional lists to match, so they go together). New profiles get one engine list everywhere, DuckDuckGo first, and the EU search engine choice screen (`force-eu-search-features`); engines' favicons aren't fetched (`break-favicons`). Decided 2026-10-14.

## Browser traffic

Decided 2026-10-21. On 2026-10-17 the Chrome Root Program used CRLSet to block six compromised eMudhra intermediate CAs. oganesson got no CRLSet: Helium's services were off, and component updates with them. Helium's `component-updates` lets only CRLSet and Widevine register, and the Chrome Root Store and the CT log list never updated. The six keys are also compiled in (`oganesson/core/emudhra-spki-block`).

The model is my own code in dubna (`components/browser_traffic`), not a copy of Helium's: dubna is GPL-2.0-only OR GPL-3.0-only, and tennessine builds no GPL-3.0 code. Helium's server URL paths are an interface it targets. `oganesson/core/browser-traffic` makes Helium's `ShouldAccess*` and `Get*URL` defer to it; Helium's prefs stay registered, derived, so its later patches keep compiling. The settings are in Local State, one set for each OS user.

| Row | Covers | Direct | Proxy |
|---|---|---|---|
| Certificate security | CRLSet, Chrome Root Store, CT log list | Google | `/com` |
| DRM | Widevine | Google | `/com` |
| Extensions | installs, item info, updates | Google | `/ext` |
| Content-blocker lists | uBlock Origin | as before | `/ubo` |
| Spellcheck dictionaries | | Google | `/dict` |
| Bangs | | none | proxy only |
| Browser updates | | WinSparkle | none |

- Each row has Download, Automatic or On request (no "Never"), and Route, Direct or Proxy, where both exist. A row offers only the routes it has.
- The Chrome Root Store and the CT log list (the PKI Metadata component) join the component allowlist. Direct component update checks go to update.googleapis.com, a narrow exception past ungoogled-chromium's request blocking and domain substitution; components send no pings.
- A proxy-only row never makes a server required: bangs stay off without one, and the row says so.
- Browser updates are a row only on a Windows per-user install. An all-users install shows it read-only; Linux shows a note that the package manager updates the browser.
- Presets, as in Tab behavior: Direct (all Automatic and Direct, the default), Through my server (all Automatic and Proxy) and Shut in (all On request, routes untouched). The preset is derived from the rows, never stored; Custom shows when they match none.
- One server for the whole browser: any helium-services server, https or http on localhost. It never falls back to direct or to Helium's host. With an invalid or no server, proxied rows stay idle.
- Health check, shown when a row uses the server: Periodically is an hourly `/connectivitycheck`; On request is Check now plus the results of real fetches. Through my server sets Periodically, Shut in On request.
- When automatic certificate data is more than 24 hours old, for any reason, the app menu gets a badge and an item that opens the page. Rows set to On request never badge.
- On request means: Certificate security, an Update now button; DRM, a prompt when a site needs Widevine (to come); Extensions, store installs and the extensions page's Update; uBlock Origin, its own Update now, as its managed storage turns its autoUpdate off; dictionaries, adding a spellcheck language; bangs, Update now; WinSparkle, Check for updates only.
- When Certificate security isn't Automatic, the page shows a red warning: revocations arrive only with a release.
- The page, Settings > Privacy and security > Browser traffic (`settings/updates`), replaces Helium's services page, and is a step of setup (above).

## Notes on carried patches

- `helium/core/ridiculous-google-compat-exceptions` (Helium 0.19.2): keeps Google sign-in, session cookies and security-key enrollment working under domain substitution. My decision, 2026-10-09.
- `upstream-fixes/tab-restore-live-tabs` (Helium 0.19.1): kept, vendored before `helium/core/lazy-session-restore`. My decision, 2026-10-08.
- `helium/core/disable-annoying-infobars` (Helium 0.19.1): kept, and it also hides the PDF infobar. My decision, 2026-10-08.
- `helium/core/prioritize-platform-policy-loading` (Helium 0.18.2): uBlock Origin reads its managed settings at startup in milliseconds, not seconds. My decision, 2026-10-02.
- `helium/ui/tab-search-in-toolbar`: tab search is a toolbar button, as Firefox's "List all tabs" is, and its bubble opens under it. My decision, 2026-10-04.
- `helium/core/mute-tab-context-menu` (Helium 0.18.3, #2631): Mute tab / Unmute tab in the tab context menu, as Firefox's "Mute Tab". My decision, 2026-10-06.
- `helium/settings/disable-safety-hub-page`: Safety Hub reports on services this build doesn't have (Safe Browsing, password leak check, updates). I reported it, 2026-10-06.
- `helium/settings/remove-safety-hub-entry-points`: same reason; removes the settings entry points to Safety Hub. I reported it, 2026-10-06. The app menu's Safety Hub notification goes with `helium/ui/app-menu-model`.
- `helium/core/open-new-tabs-next-to-active-tab-option`: kept for its pref and switch, one of Tab behavior's knobs: Firefox's `browser.tabs.insertAfterCurrent`. Turned on, it leaves the Chromium preset, so Firefox's rules place the tab and the patch's own placement in `AddTab` no longer runs; the patch stays whole to stay comparable with upstream.
- `ungoogled-chromium/add-flag-to-close-window-with-last-tab`: Firefox's `browser.tabs.closeWindowWithLastTab`. My decision, 2026-10-11.
- `helium/core/close-tabs-to-left`: "Close tabs to the left", as in Firefox's tab menu. My decision, 2026-10-11.
- `helium/core/hibernate-tab-context-menu`: unloads a tab from the tab menu, as Firefox's "Unload Tab"; Memory Saver stays off by default. My decision, 2026-10-11.
- `helium/core/network/global-privacy-control-pref`: a Global Privacy Control setting, as in Firefox. My decision, 2026-10-11.
- `helium/core/network/disable-ech-flag`: adds a flag only. My decision, 2026-10-11.
- `helium/core/network/quic-v2-flag`: adds a flag only. My decision, 2026-10-11.
- `helium/core/network/split-clienthello`: adds a flag only. My decision, 2026-10-11.
- `helium/core/network/ignore-system-proxy-server-flag`: adds a flag only. My decision, 2026-10-11.
- `helium/ui/show-tabs-from-non-account-backends`: History's "Tabs from other devices" shows Firefox Sync's open tabs without a Google sign-in (`oganesson/core/firefox-sync-remote-tabs`). My decision, 2026-10-11.

## Taken from ungoogled-chromium, not in Helium (1)

Mine, in `patches/series`; `tools/update_helium.py` doesn't track them, so refresh them from ungoogled-chromium by hand.

- `ungoogled-chromium/keep-expired-flags` (ungoogled-chromium `ffeb45a`): expired `chrome://flags` entries stay usable. Helium replaced it with `exclude-irrelevant-flags`, which I drop. My decision, 2026-10-11.
