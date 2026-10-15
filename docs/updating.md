# Updating the browser

1. Run `python3 tools/update_helium.py --dry-run LINUX_TAG`. It lists the patches Helium adds and removes. Oganesson carries every Helium patch it doesn't drop, so review the new ones against the scope in `goals.md`.
2. For a new patch that isn't wanted: if no later Helium patch builds on it, add it to `patches/helium-drops.txt` with the reason; otherwise carry it and turn its feature off in my patches. Record the decision in `helium-patch-decisions.md`. Then run the updater without `--dry-run`, which moves the `helium` and `linux/helium-linux` submodules.
3. Run `./oganesson.py check-patches --keep work/rebase`. Helium's own patches apply as they are; resolve my failures with `python3 tools/regen.py work/rebase`. Review every changed hunk, including mechanically refreshed patches. Never edit Helium's patches: fix mine, or drop theirs.
4. Run the fast checks and a clean patch check. Build the browser and run the retained browser test suites.
5. Record the exact source commit used for the verified binary. Package only that build after release acceptance.

Keep emergency Chromium security updates distinct from product changes. A new upstream pin and clean patch application are intermediate results. They do not prove that a copied adapter or a changed upstream API still behaves correctly.

To update Mozilla application-services, use `dubna/tools/update_app_services.py TAG`, review the locked dependencies, then rebuild and test Sync on both products. The library and the browser adapters share a JSON contract.
