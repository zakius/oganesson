# Working on oganesson

Read `goals.md` for scope and `README.md` for commands. Product code belongs in `src/`; small feature patches connect it to Chromium. The three series files define application order.

For source changes, run `sh tools/hooks/pre-commit` and a clean `./oganesson.py check-patches`. Browser behavior requires a build and the affected browser suites. Report unrun checks explicitly; source assembly is not runtime verification.

Builds and scratch files belong under ignored `work/`. Use an isolated checkout and `tools/detach.sh` for long jobs. Keep user profiles separate. Read `docs/firefox-sync.md` before changing Sync, and `docs/updating.md` before changing upstream pins.
