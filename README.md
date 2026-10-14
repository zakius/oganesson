# oganesson

> **Highly volatile.** This is a personal project. Features change or disappear without notice, some may misbehave, updates can break things, and development may stop at any moment. Use it knowing that.

A Linux Chromium browser source layer for mouse gestures, a configurable toolbar, full Chromium uBlock Origin, hidden tab close buttons, middle-click new tabs, Firefox tab rules, Firefox Sync, installed web app controls, and switches that stop saving browsing and download history.

This repository is a focused feature set taken from the earlier oganesson-core (gone; its issues and the oldest repo's patches are archived locally). It keeps the Helium patch baseline and existing build tools. Product code lives in `src/`, with feature patches in `patches/oganesson/`. What it shares with [tennessine](https://github.com/zakius/tennessine), the Android browser (Firefox Sync, no saved history), is in the `dubna` submodule ([zakius/dubna](https://github.com/zakius/dubna)): clone with `--recurse-submodules`, or run `git submodule update --init`. The Chromium checkout and build outputs live in ignored `work/`.

## What it's for

A browser that is complete for the way its maintainer uses it, not one that tries to do everything: Vivaldi shows where that leads, with so many features that some never work well. What an extension does well stays an extension's job. Content blocking is uBlock Origin, the state of the art, built in through Helium's work. The browser itself only builds what an extension can't do: mouse gestures that work on every page, internal ones included, a toolbar whose every item moves and hides, Firefox's tab placement and close selection, Firefox-compatible Sync for passwords, bookmarks, history, tabs, addresses and cards, best with your own self-hosted sync server, installed web apps whose outside links open in the default browser, and switches that stop saving history.

## The name

Oganesson (Og, element 118) sits in the same group as helium, which this browser is built on, at the other end of it: helium is the lightest noble gas, oganesson the heaviest. The name was picked for that, same group as Helium but not lightweight. It is only nominally a noble gas: calculations predict it is a solid at room temperature, and far more reactive than the rest of its group. That fits too.

Its Android sibling, [tennessine](https://github.com/zakius/tennessine), is named after its neighbour, element 117. That both were first made in Dubna, at the Joint Institute for Nuclear Research (oganesson in 2002, tennessine in 2010), is a coincidence, and the name of the [code they share](https://github.com/zakius/dubna).

## Build and check

Requires Linux x86-64, Python 3, Git, Docker, and space for a Chromium build. The first build can take hours.

```sh
./oganesson.py check-patches
./oganesson.py build -j 16 --nice 19
./oganesson.py test gestures toolbar tab_behavior firefox_sync ubo_restart web_app_links shortcuts
./oganesson.py run
```

Browser tests also require Xvfb, xdotool, and xwd. They use throwaway profiles. `run` uses `work/profile`. Launching the binary directly uses the separate `oganesson-focused` profile directory. The binary remains named `oganesson`; packaging must be reviewed before installing it beside the existing browser.

`./oganesson.py build --release` builds the release configuration. Run a long build through `tools/detach.sh LOG -- ./oganesson.py build ...` when it must survive the terminal session. The build process takes a checkout lock.

`check-patches` applies the whole series to the pinned sources with zero fuzz, without compiling. It does not replace a browser build.

## Scope and maintenance

[Architecture and provenance](docs/architecture.md) explains the upstream choice, retained dependencies, and exclusions. [Updating](docs/updating.md) describes upgrading Helium and Chromium. [Installed web apps](docs/web-apps.md) covers the PWA controls. [Address bar suggestions](docs/omnibox.md) lists the suggestion switches and describes their order and site autofill. [Autoplay](docs/autoplay.md) describes the Firefox-style autoplay setting. [Firefox Sync](docs/firefox-sync.md) records the protocol boundary and validation requirements.

The patch order is authoritative in `patches/series`, `linux/patches/series`, and `late/series`. `chromium_version.txt`, `upstream.txt`, `deps.ini`, and Rust's `Cargo.lock` pin the inputs. Preserve inherited licenses and copyright notices.
