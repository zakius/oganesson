# Updating the browser

1. Run `python3 tools/update_helium.py --dry-run LINUX_TAG`. Review new upstream patches against the scope in `goals.md`.
2. Update the decisions in `helium-patch-decisions.md`, then run the updater without `--dry-run`. Inspect its merge-conflict report even when no conflict markers remain.
3. Run `./oganesson.py check-patches --keep work/rebase`. Resolve failures with `python3 tools/regen.py work/rebase`. Review every changed hunk, including mechanically refreshed patches.
4. Run the fast checks and a clean patch check. Build the browser and run the retained browser test suites.
5. Record the exact source commit used for the verified binary. Package only that build after release acceptance.

Keep emergency Chromium security updates distinct from product changes. A new upstream pin and clean patch application are intermediate results. They do not prove that a copied adapter or a changed upstream API still behaves correctly.

To update Mozilla application-services, use `tools/update-app-services.sh TAG`, review the locked dependencies, then rebuild and test Sync. The library and the browser adapters share a JSON contract.
