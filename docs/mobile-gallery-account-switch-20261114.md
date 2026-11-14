# Native clinical gallery account-switch regression — 2026-11-14

## Web/mobile functional comparison
The web patient profile has patient-scoped clinical media, protected previews and an analysis action. The native `NativePatientMedia` component implements the same flow with a token and patient ID scope, but its async gallery loader previously retained a shared `loadLock` across a scope change.

## Reproduced from source
Before this patch, a gallery request for account A could remain pending while navigation changed to account B. The new component effect called `loader.current()`, but `loadLock.current` was still true, so no B request was started. When A's request eventually completed, its `finally` block did not release the lock because `current()` was false. The B gallery could therefore remain empty without loading. The prior account's pending mutation and viewer state also needed explicit reset.

## Fix and regression
- Invalidate the old request generation and clear the gallery loading lock on patient/account change.
- Reset pagination, visible items, selection, preview, viewer, progress, mutation lock and error before loading the new scope.
- Preserve the existing response-scope checks so a late response from account A cannot populate B's gallery.
- Add `mobile/tests/patientMediaAccountSwitch.cjs` using a deferred A response and immediate B response, and include it in `npm run test:beta`.

## Verification limits
The GitHub source updates were committed, but no full `npm ci`, TypeScript run, Node regression execution or physical-device test was available in this connector-only run. This is a targeted source-level race fix, not proof that the APK's other spinners are solved.

The last inspected Mobile Android CI run `43602106932` had failed typecheck and beta-apk jobs with no job steps exposed; downloading either job log returned BlobNotFound 404. This is not enough evidence to assign a TypeScript root cause.

Next: execute the regression and full mobile test suite in a runnable checkout; inspect the native gallery with two authenticated accounts and deliberately delayed requests, then address any remaining failures before an APK build. No main merge or deployment.
