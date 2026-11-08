# Product scope

Linux x86-64 first. Keep mouse gestures, movable toolbar items, full Chromium uBlock Origin, hidden tab close buttons, middle-click on empty tab-bar space to open a tab, Firefox tab placement and close selection, Firefox Sync, and installed web app (PWA) controls: out-of-scope links open in the default browser, per-app scope rules, and a per-app start address. Keep tab containers, shared with tennessine through dubna ([docs](docs/containers.md)); they sync through Multi-Account Containers' own `storage.sync` data, not a containers engine of ours ([docs](docs/firefox-sync.md#containers)).

Keep Chromium's existing extension support and Helium's Manifest V2/uBO maintenance. Translation additions, Firefox theme APIs, and unrelated visual changes are outside this fork's scope.

## Parked

Planned, not started, in this order. Decided 2026-10-20.

1. **Firefox add-ons, uBO first.** Upstream uBlock Origin's Firefox build from AMO must run, so uBO doesn't depend on Helium maintaining a Chromium fork with CNAME uncloaking. Then Multi-Account Containers (a must-have unless containers do its job natively), then the most popular add-ons, a chunk at a time. Order for uBO: `.xpi` install, Gecko IDs and AMO updates (in the archive); promise-returning blocking listeners and `dns.resolve` without a request URL; `proxyInfo` and `documentUrl` in webRequest details and the `menus` alias; `contentScripts.register` for scriptlets; then switch from Helium's uBO. `filterResponseData`, the `moz-extension` origin and holding requests until filters load are large and optional. The `contextualIdentities`/`cookieStoreId` layer that ran MAC was in oganesson-core, now deleted; only its PR text survives in the archive.
2. **Stretch:** container windows (a window whose tabs all open in one container), and a command palette with its own shortcut that searches and runs any browser or extension command.

Firefox bookmark keywords and separators stay in the Sync store only: the browser does not show them, and Sync keeps them for Firefox. There is no separate search bar.

Firefox tab rules are the default, with a Chromium preset and a few knobs in Settings; the tab strip patch stays small, with the logic in its own file. User data uses an isolated profile until migration has dedicated validation.
