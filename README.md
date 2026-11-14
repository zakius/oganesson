# oganesson

oganesson is a desktop Chromium browser built on [Helium](https://github.com/imputnet/helium). It adds mouse gestures, a toolbar whose items move and hide, and Firefox tab placement and close selection. It also has Firefox-compatible Sync, controls for installed web apps, tab containers, and switches that stop saving history. It runs on Linux x86-64 and Windows x64. Its Android sibling is [tennessine](https://github.com/zakius/tennessine), and the code the two share is in [dubna](https://github.com/zakius/dubna).

> **Highly volatile.** This is a personal project. Features change or disappear without notice, some may misbehave, updates can break things, and development may stop at any moment. Use it knowing that.

## What it's for

oganesson is meant to be complete for the way I use it. It does not try to do everything. Vivaldi tries to do too much, and some of its features never work well.

Where an extension does the job well, the job stays with the extension. Content blocking is uBlock Origin, the state of the art, built in through Helium's work. The browser builds natively only what an extension can't do:

- Mouse gestures that work on every page, internal pages included.
- A toolbar where every item moves and hides.
- Firefox's tab placement and close selection, with Chromium's as a preset and each rule a setting.
- Firefox-compatible Sync for passwords, bookmarks, history, tabs, addresses and cards. It works best with a self-hosted sync server.
- Installed web apps that open outside links in the default browser.
- Containers: separate cookies and site data for the tabs of each container, as Firefox and Brave have, with rules that open chosen sites in a container.
- Switches that stop saving browsing and download history.

oganesson is not privacy-paranoid. It keeps features that some privacy-focused browsers remove, because they are useful: the built-in password manager, Sync, and Google among the search engines. Each one is yours to skip. DuckDuckGo is the default search engine, Sync stays off until you sign in, and saving passwords can be turned off in settings. If you don't trust a feature, don't use it.

[goals.md](goals.md) sets out what is in scope and what isn't.

## The name

Oganesson (Og, element 118) is in the same group as helium, and the browser is built on Helium. The name was picked for that: same group as Helium, but not lightweight. Helium is the lightest noble gas, oganesson the heaviest. It is also only nominally a noble gas. Calculations predict that it is a solid at room temperature and far more reactive than the rest of its group, which fits the project too.

tennessine is named after oganesson's neighbour, element 117. Both elements were first made at the Joint Institute for Nuclear Research in Dubna: oganesson in 2002, with Lawrence Livermore National Laboratory, and tennessine in 2010. That is a coincidence, and it gave the shared repo, [dubna](https://github.com/zakius/dubna), its name.

## Install

Release builds are in a signed apt and dnf repository for x86-64-v2 machines. [docs/packages.md](docs/packages.md) shows how to add it.

On Windows, an installer and a zip to unpack anywhere are on the [site](https://dubna.zakius.xyz/install.html#windows). They have no Authenticode signature. A per-user install updates itself; an all-users install updates by hand ([docs/windows.md](docs/windows.md)).

The browser keeps its own profile in `~/.config/oganesson`, separate from Helium's and Chromium's (on Windows, `%LOCALAPPDATA%\oganesson`). A profile in `~/.config/oganesson-focused`, its name before October 2026, moves there on the first start.

## Layout

| Path | What |
|---|---|
| `helium/` | Submodule at the Helium commit that helium-linux builds on. Its patch series applies as it is, minus `patches/helium-drops.txt`. Never edited: what I don't want from Helium is dropped there or turned off by my patches ([decisions](docs/helium-patch-decisions.md)). |
| `linux/` | The Linux build (`container-build.sh`), packaging and publishing, and the `helium-linux` submodule with its platform patches. |
| `windows/` | The Windows build, cross-compiled on Linux: its container, toolchain, Sync library and packaging, and the `helium-windows` submodule with its platform patches ([docs/windows.md](docs/windows.md)). |
| `dubna/` | Submodule: [dubna](https://github.com/zakius/dubna), the code, patches and translations shared with tennessine. |
| `patches/` | My patches (`series`), applied after Helium's and helium-linux's. Also `helium-drops.txt`, and `helium-utils.patch` with my fixes to Helium's build tools. |
| `late/` | Patches applied after the platform's: branding for every platform. Each platform's own renames of what its Helium repo sets are in `linux/late/` and `windows/late/`. |
| `src/` | My new files, copied over the Chromium tree after `dubna/src/`. |
| `resources/` | My branding, laid over Helium's resources. |
| `l10n/` | Polish translations of my strings. |
| `tools/` | Patch tools (`check_patches.py`, `regen.py`, `amend.py`, `update_helium.py`), the browser tests (`e2e/`), screenshots for dubna's site (`screenshots.py`), the branding and the app icon variants, drawn from the Og glyph (`branding_icons.py`, `og.svg`), and job helpers. |
| `oganesson.py` | Every command: `build`, `test`, `run`, `check-patches`, `stamp`, `shell`, `snapshot`. |

`oganesson.py` assembles Helium's tree in `work/helium-tree` from the submodule, with `helium-utils.patch` applied, my branding added and the drops left out of its series. Builds and scratch files live in `work/`, which Git ignores.

## Build and check

A build needs Linux x86-64, Python 3, Git, Docker, and room for a Chromium build. The first build takes hours. Clone with `--recurse-submodules`, or run `git submodule update --init` after cloning.

```sh
./oganesson.py check-patches            # every patch, zero fuzz, without compiling
./oganesson.py build --release          # without --release: the dev build
./oganesson.py build --windows          # the Windows build and its packages (docs/windows.md)
./oganesson.py test --release           # all browser tests, or name suites: toolbar web_app_links
./oganesson.py test --release --repeat 10   # each test 10 times, listing the flaky ones
./oganesson.py run                      # the dev build, with the profile in work/profile
```

The browser tests need Xvfb, xdotool and xwd, and use throwaway profiles. Each test class has its own browser and X display, so classes run side by side, as many as a quarter of the CPUs and at most eight (`-j`). `-j1` runs them one after another, with unittest's output as it comes.

A build takes the checkout's lock. To keep a build running after the terminal closes, start it with `tools/detach.sh LOG -- ./oganesson.py build ...`. A build runs one compile job per CPU of the machine, unless `-j` says otherwise; how many CPUs the containers get is up to the system.

Release builds keep one Chromium PGO profile per milestone, pinned in `pgo-profiles.txt`, so a patch update rebuilds only what changed ([docs/updating.md](docs/updating.md#pgo-profiles)).

`check-patches` doesn't replace a build, because some breakage only shows when the code compiles or runs. Run the pre-commit checks (`sh tools/hooks/pre-commit`) before you commit.

## Updating

[docs/updating.md](docs/updating.md) has the full procedure. In short, `tools/update_helium.py` moves the `helium`, `linux/helium-linux` and `windows/helium-windows` submodules to a helium-linux release and the matching helium-windows one, and lists the patches Helium and helium-windows add and remove. Then check the patches, fix mine, build and test. dubna's [update policy](https://github.com/zakius/dubna#update-policy) says when to update.

## Releasing

A merge to main only merges. To release, push a tag whose name starts with `release-` on a commit of main (dubna's [Releases](https://github.com/zakius/dubna#releases) has the command), or start `.github/workflows/release.yml` by hand. The workflow releases main's tip and runs these steps on the build machine's runner. It posts the [GitHub release](https://github.com/zakius/oganesson/releases), with the Linux packages and notes from the commits, before it publishes to the package repository, and adds the Windows packages to it before it publishes them to the site. So several tasks can land one at a time and release in one build. The Windows build starts once the Linux tests pass and runs while Linux packs and uploads. The build machine uploads each package once, to the GitHub release: the package repository's and the site's server downloads it from there and checks it against the local file (`tools/from-github.sh`), and rsync sends only what the release doesn't have. The steps:

```sh
./oganesson.py build --release
./oganesson.py test --release
./oganesson.py build --windows          # in the background; packages in work/dl/windows
linux/pack.sh                           # then the GitHub release, with the Linux packages
linux/publish-repo.sh                   # the server gets the new .deb and .rpm
windows/publish.sh                      # after the Windows packages join the GitHub release
```

[docs/packages.md](docs/packages.md) covers the repository. The version is Chromium's, plus the commit time in the release field.

## Docs

[Architecture](docs/architecture.md), [Helium patch decisions](docs/helium-patch-decisions.md), [Firefox-compatible Sync](docs/firefox-sync.md), [mouse gestures](docs/mouse-gestures.md), [toolbar](docs/toolbar.md), [tab behavior](docs/tab-behavior.md), [installed web apps](docs/web-apps.md), [containers](docs/containers.md), [address bar suggestions](docs/omnibox.md), [autoplay](docs/autoplay.md), [app icon](docs/app-icon.md), [packages](docs/packages.md), [Windows](docs/windows.md), [updating](docs/updating.md).

## License

GPL-3.0 (`LICENSE`). Preserve inherited licenses and copyright notices, including those of the projects whose patches I carry, in `helium/`.
