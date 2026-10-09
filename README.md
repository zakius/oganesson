# oganesson focused

A Linux Chromium browser source layer for mouse gestures, a configurable toolbar, full Chromium uBlock Origin, hidden tab close buttons, middle-click new tabs, Firefox tab rules, Firefox Sync, installed web app controls, and switches that stop saving browsing and download history.

This repository extracts a focused feature set from [oganesson-core](https://github.com/zakius/oganesson-core). It keeps the Helium patch baseline and existing build tools. Product code lives in `src/`, with feature patches in `patches/oganesson/`. The Chromium checkout and build outputs live in ignored `work/`.

**Status:** source extraction under validation. This repository is not a tested browser release. Patch application and tooling checks do not establish browser behavior. The first full build, browser tests, and real-account Sync verification are release gates.

## Build and check

Requires Linux x86-64, Python 3, Git, Docker, and space for a Chromium build. The first build can take hours.

```sh
./oganesson.py check-patches
./oganesson.py build -j 16 --nice 19
./oganesson.py test gestures toolbar tab_behavior firefox_sync ubo_restart web_app_links
./oganesson.py run
```

Browser tests also require Xvfb, xdotool, and xwd. They use throwaway profiles. `run` uses `work/profile`. Launching the binary directly uses the separate `oganesson-focused` profile directory. The binary remains named `oganesson`; packaging must be reviewed before installing it beside the existing browser.

`./oganesson.py build --release` builds the release configuration. Run a long build through `tools/detach.sh LOG -- ./oganesson.py build ...` when it must survive the terminal session. The build process takes a checkout lock.

`check-patches` applies the whole series to the pinned sources with zero fuzz, without compiling. It does not replace a browser build.

## Scope and maintenance

[Architecture and provenance](docs/architecture.md) explains the upstream choice, retained dependencies, and exclusions. [Updating](docs/updating.md) describes upgrading Helium and Chromium. [Installed web apps](docs/web-apps.md) covers the PWA controls. [Firefox Sync](docs/firefox-sync.md) records the protocol boundary and validation requirements.

The patch order is authoritative in `patches/series`, `linux/patches/series`, and `late/series`. `chromium_version.txt`, `upstream.txt`, `deps.ini`, and Rust's `Cargo.lock` pin the inputs. Preserve inherited licenses and copyright notices.
