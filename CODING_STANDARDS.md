# Source changes

Keep one logical feature per patch. New files belong in `src/` and must have build wiring. Keep upstream patch changes small and preserve licenses.

Run the fast checks and apply every patch with zero fuzz. Changes to browser behavior need a successful build and the affected browser tests before release. State when a build or runtime check remains unrun.

Preserve validation, encryption, cancellation, and conflict handling at Sync boundaries. Keep exact dependencies pinned. Document product dependencies in `docs/architecture.md` when they extend the apparent feature scope.

Put user-visible text in `.grd`/`.grdp` messages, never literal English in code. Our `.grdp` files are parts of `chrome/app/oganesson_strings.grd`, not of Chromium's `generated_resources.grd`: code that uses their messages, a patched Chromium file too, includes `chrome/grit/oganesson_strings.h`. A new string then recompiles only those files. Give every message an English source and a Polish translation in `l10n/pl.json` (`dubna/l10n/pl.json` for strings in `dubna/`); `dubna/tools/translate.py --check dubna .` (in the pre-commit hook) lists the missing ones. The build renames Chrome and Chromium to the product name in every message, so a message that must name Chromium takes it as a placeholder argument. In an inline TS `html` template, use `[[i18n('key')]]` with `I18nMixin`: Chromium only replaces `$i18n{key}` in templates built from `.html` files.
