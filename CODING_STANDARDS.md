# Source changes

Keep one logical feature per patch. New files belong in `src/` and must have build wiring. Keep upstream patch changes small and preserve licenses.

Run the fast checks and apply every patch with zero fuzz. Changes to browser behavior need a successful build and the affected browser tests before release. State when a build or runtime check remains unrun.

Preserve validation, encryption, cancellation, and conflict handling at Sync boundaries. Keep exact dependencies pinned. Document product dependencies in `docs/architecture.md` when they extend the apparent feature scope.
