# Updating the browser

1. Run `python3 tools/update_helium.py --dry-run LINUX_TAG`. It lists the patches Helium and helium-windows add and remove. Oganesson carries every patch it doesn't drop, so review the new ones against the scope in `goals.md`. helium-windows tags the same version on the same Helium commit, usually some hours after helium-linux. Until that tag exists, the updater leaves `windows/helium-windows` where it is and exits 1. Run it again when the tag is out.
2. For a new patch that isn't wanted: if no later patch builds on it, add it to `patches/helium-drops.txt` (Helium's) or `windows/helium-windows-drops.txt` (helium-windows') with the reason; otherwise carry it and turn its feature off in my patches. Remove a drop that the updater reports the new series no longer has. Record the decision in `docs/helium-patch-decisions.md`. Then run the updater without `--dry-run`, which moves the `helium`, `linux/helium-linux` and `windows/helium-windows` submodules.
3. Run `./oganesson.py check-patches --keep work/rebase`. It checks the Linux series and then the Windows series, and reports the failures of each. Helium's own patches apply as they are; resolve my failures with `python3 tools/regen.py work/rebase`, and the ones only the Windows series has with `python3 tools/regen.py work/rebase --windows`, which works on `work/rebase/src-windows`. A patch regen rewrites for one series can break the other: check both again. Review every changed hunk, including mechanically refreshed patches. Never edit Helium's patches: fix mine, or drop theirs.
4. Run the fast checks and a clean patch check. Build the browser and run the retained browser test suites.
5. Record the exact source commit used for the verified binary. Package only that build after release acceptance.

Keep emergency Chromium security updates distinct from product changes. A new upstream pin and clean patch application are intermediate results. They do not prove that a copied adapter or a changed upstream API still behaves correctly.

## PGO profiles

Release builds compile every file with Chromium's PGO profile, and Chromium ships a new profile with every release, even a patch release. So within a milestone the release builds keep one profile: the one `pgo-profiles.txt` pins for Linux (`linux`) and Windows (`win64`). The number after the target in a profile's name (`chrome-linux-8103-...`) is the milestone's branch, the third part of its versions (157.0.8103.78). A patch update then rebuilds only what changed; the profile is up to a few weeks older, which `-Wno-profile-instr-out-of-date` already allows for.

`pinned_pgo_profile` in `tools/prepare.sh` writes the GN argument `pgo_data_path` when the tree's own profile (`chrome/build/linux.pgo.txt`, `win64.pgo.txt`) is another of the same branch, and `patches/oganesson/core/pgo-pinned-profile.patch` stops the tree's `.pgo.txt` from rebuilding everything then. A copy of the pinned file in the build folder (`work/helium-linux/build/pgo-profiles`, `work/helium-windows/build/pgo-profiles`) outlives Chromium's pruning of unused profiles. When the pin is another milestone's, or its file is gone, the build takes the tree's own profile, says so in its log, and rebuilds everything.

On a new milestone, `tools/update_helium.py` pins the new version's profiles: commit `pgo-profiles.txt` with the update.

V8's patch level also changes with every release, in `v8/include/v8-version.h`. `patches/oganesson/core/v8-version-include.patch` takes that header out of `v8.h`, so only the few files that read the version recompile, not every file that uses V8.

To update Mozilla application-services, use `dubna/tools/update_app_services.py TAG`, review the locked dependencies, then rebuild and test Sync on both products. The library and the browser adapters share a JSON contract.
