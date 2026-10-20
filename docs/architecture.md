# Upstream strategy

Keep Helium's ordered patch series as it is, my patches after it, and place new product code in separate `src/` files. Helium, helium-linux and helium-windows are submodules, never edited: what I don't want of them is either dropped (`patches/helium-drops.txt`, `windows/helium-windows-drops.txt`, only for patches nothing later builds on) or turned off by my patches. This fits the selected features better than an embedding framework or a large replacement UI. Tab placement, toolbar layout, and mouse event handling need native browser integration. A framework would add browser-shell work without removing the Chromium maintenance beneath it.

Helium supplies the full Chromium uBO integration and the Manifest V2 support it needs. Following that work avoids owning those changes alone. It also introduces dependency on Helium's release timing and carries its baseline privacy/UI changes. The alternative is a direct Chromium fork with fewer inherited choices and more responsibility for extension support. For this scope, reuse wins until a concrete Helium change makes that tradeoff unfavorable.

Keep feature patches separate. Hooks that every feature needs are in `patches/oganesson/core/hooks.patch`, the first of my patches, so a feature adds to `src/` instead of patching them: its strings in `src/chrome/app/oganesson_strings.grdp`, its profile prefs in `src/chrome/browser/prefs/oganesson_prefs.h`, its settings prefs in `src/chrome/browser/extensions/api/settings_private/oganesson_prefs_allowlist.h`, and its settings strings and message handlers in `src/chrome/browser/ui/webui/settings/oganesson_settings.cc`. The settings sources are listed in that patch's two `BUILD.gn` hunks. Features shared with tennessine keep their files in the `dubna` submodule instead: `dubna/src/` goes into the tree before `src/`, `dubna/patches/` holds their patches (listed in `patches/series` as `../dubna/patches/…`), and each such feature registers its own prefs, so it doesn't depend on desktop's hooks. Avoid copying existing Chromium files into `src/`: those files can silently conceal upstream fixes. During upgrades, inspect build and behavioral failures as well as patch rejects.

## Source provenance

Initial extraction: oganesson-core (since deleted) at `f0b39417cd03c7adf13518027a3f0269af99ec60`, inspected 2026-10-09. The inherited baseline pins Helium to `8309d0e93a7c728e8cbc06f3f112bc457c235793` and helium-linux to `0.19.1.2`. The pins are now the `helium` and `linux/helium-linux` submodules (Chromium's version is `helium/chromium_version.txt`). Since 2026-10-14 oganesson carries Helium's whole series, minus the patches in `patches/helium-drops.txt`, instead of a hand-picked subset that needed 21 of Helium's patches edited to apply.

uBO comes from the pinned Chromium package in `deps.ini`. It is full uBO, not uBO Lite, and not the Firefox XPI. Running the Firefox XPI instead is parked ([goals](../goals.md#parked)).

Firefox Sync keeps the separate Rust library using Mozilla application-services and native C++ store adapters. General Firefox extension compatibility is not a prerequisite for that protocol integration. Sync has no containers engine: containers are parked, and their sync would come from Multi-Account Containers' `storage.sync`.

Firefox bookmark keywords and separators stay in the Sync store only. Mouse gestures retain browser commands and standard Chromium extension actions, without Firefox page-action emulation. Tab selection retains Chromium extension opener handling, without Firefox hidden-tab APIs.

## Release acceptance

A release needs a successful build and tests for gestures, toolbar persistence, tab opening/closing, uBO blocking across restart, and each supported Sync data type. Test profile migration independently. Fake-server tests cannot prove Mozilla production compatibility or interoperability with Fenix.

The original Sync implementation uses application-services' example OAuth client ID. A supported production OAuth identity and real-account/Fenix tests remain release questions. Preserve encrypted token storage, server backoff, sign-out cancellation, and protection against overwriting local edits during a sync.

The source extraction does not change the installed browser or reuse its profile. No binary or package is published by repository setup.
