# oganesson

A desktop Chromium browser layered on [Helium](https://github.com/imputnet/helium): mouse gestures, a toolbar whose items move and hide, full Chromium uBlock Origin, Firefox tab placement and close selection, Firefox Sync, installed web app controls, and switches that stop saving browsing and download history. Linux x86-64 today; Windows is planned (`windows/`, not there yet). [goals.md](goals.md) says what is in scope and what isn't.

Its Android sibling is [tennessine](https://github.com/zakius/tennessine). What the two share (Firefox Sync, no saved history, the Chromium update policy) is in [dubna](https://github.com/zakius/dubna).

## Install

Release builds are in a signed apt and dnf repository for x86-64-v2 machines: see [docs/packages.md](docs/packages.md) for adding it. The browser uses its own profile (`~/.config/oganesson-focused`), apart from Helium's or Chromium's.

## Layout

| Path | What |
|---|---|
| `helium/` | Submodule at the Helium commit helium-linux builds on. Its patch series applies as it is, minus `patches/helium-drops.txt`. Never edited: what we don't want of Helium is dropped there, or turned off by our patches ([decisions](docs/helium-patch-decisions.md)). |
| `linux/` | Linux's build (`container-build.sh`), packaging and publishing, and the `helium-linux` submodule with its platform patches. |
| `dubna/` | Submodule: the code, patches and translations shared with tennessine. |
| `patches/` | Our patches (`series`), applied after Helium's and helium-linux's. Also `helium-drops.txt`, and `helium-utils.patch`, our fixes to Helium's build tools. |
| `late/` | Patches applied after the platform's, which rename what it sets (branding). |
| `src/` | Our new files, copied over the Chromium tree after `dubna/src/`. |
| `resources/` | Our branding, laid over Helium's resources. |
| `l10n/` | Polish translations of our strings. |
| `tools/` | Patch tools (`check_patches.py`, `regen.py`, `amend.py`, `update_helium.py`), the browser tests (`e2e/`), and job helpers. |
| `oganesson.py` | Every command: `build`, `test`, `run`, `check-patches`, `stamp`, `shell`, `snapshot`. |

`oganesson.py` assembles Helium's tree in `work/helium-tree`: the submodule, with `helium-utils.patch` applied, our branding, and the drops left out of its series. Builds and scratch files live in the ignored `work/`.

## Build and check

Needs Linux x86-64, Python 3, Git, Docker, and room for a Chromium build: the first build takes hours. Clone with `--recurse-submodules`, or run `git submodule update --init` after cloning.

```sh
./oganesson.py check-patches            # every patch, zero fuzz, without compiling
./oganesson.py build --release          # or without --release: the dev build
./oganesson.py test --release           # all browser tests, or name suites: toolbar web_app_links
./oganesson.py run                      # the dev build, with the profile in work/profile
```

Browser tests need Xvfb, xdotool and xwd, and use throwaway profiles. A build takes the checkout's lock; one that must outlive the terminal runs through `tools/detach.sh LOG -- ./oganesson.py build ...`. Weekday daytime builds run at low priority unless `-j` or `--nice` says otherwise.

`check-patches` doesn't replace a build: some breakage only shows when the code compiles or runs. Run the pre-commit checks (`sh tools/hooks/pre-commit`) before committing.

## Releasing

`./oganesson.py build --release`, `./oganesson.py test --release`, then `linux/pack.sh` and `linux/publish-repo.sh` ([packages](docs/packages.md)). The version is Helium's, plus the commit time.

## Updating

[docs/updating.md](docs/updating.md): `tools/update_helium.py` moves the `helium` and `linux/helium-linux` submodules to a helium-linux release and lists the patches Helium adds and removes; then check, fix our patches, build and test. dubna's [update policy](https://github.com/zakius/dubna#update-policy) says when.

## Docs

[Architecture](docs/architecture.md), [Helium patch decisions](docs/helium-patch-decisions.md), [Firefox Sync](docs/firefox-sync.md), [mouse gestures](docs/mouse-gestures.md), [toolbar](docs/toolbar.md), [tab behavior](docs/tab-behavior.md), [installed web apps](docs/web-apps.md), [address bar suggestions](docs/omnibox.md), [autoplay](docs/autoplay.md), [packages](docs/packages.md).

Preserve inherited licenses and copyright notices: GPL-3.0 (`LICENSE`), and the licenses of the projects whose patches we carry, in `helium/`.
