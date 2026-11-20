# Native CI and account-erasure follow-up — 2026-11-20

## Verified starting point

PR #257 was open, Draft, and not merged. Its head at the start of this work was
`c21022b146d1154672be6f802d57c3ac0eeb73f9`. The branch name was confirmed
against the PR head. No main merge, production deployment, migration, APK
publication, or patient-data mutation was performed.

## Current-head GitHub Actions evidence

The new diagnostics commit made the workflow output useful. The following runs
were attached to the exact starting head `c21022b`:

- Android run `44714247189`:
  - `typecheck`: TypeScript step passed; session and realtime/pagination tests
    passed; the beta regression step failed; Android/iOS Expo JS export passed.
  - `beta-apk`: Gradle internal release assembly passed and uploaded the
    `dental-ai-beta-arm64` artifact. This is a build artifact, not a published
    APK or device acceptance.
- Security Recovery run `44714246990`:
  - native academic, social, voice and program jobs passed.
  - native clinical security failed one Node test.
  - Python security failed with 50 failed, 484 passed, 728 warnings.
  - Diagnostic artifacts were uploaded successfully.

### Android beta regression root cause

Eight tests failed for a shared test-loader issue, not an Android type error:

- Three `patientAnalysisHistory.cjs` tests and one
  `patientHistoryRetry.cjs` test attempted to load the TypeScript-only
  `appResumeRefresh.ts` through raw CommonJS `require()`, producing
  `Unexpected token ':'`.
- Four `toothChartFocusApi.cjs` tests loaded
  `patientDirectoryPresentation.ts` through raw `require()`, producing
  `Unexpected token 'export'`.

The tests now transpile those pure TypeScript helpers with the already-installed
TypeScript compiler before evaluating them in the VM harness. This removes the
Node 24 raw-TS loader dependency without changing application behavior.

## Account-erasure security correction

The canonical web route rejects an administrator with HTTP 409 before password
confirmation. The native adapter previously depended on `_account_user`, which
runs the administrator step-up gate first; an administrator without a verified
admin session therefore received 403 rather than the same web exclusion.

The native delete route now uses the authenticated mobile user and applies the
unconditional `ADMIN` exclusion before delegating to the canonical web handler.
The regression covers both an unverified admin session and a verified admin
session, and asserts that the account remains active with its email intact.

## Account-erasure data scope reviewed

The existing coordinator deliberately distinguishes account identity from
third-party clinical records:

- Guest analyses and guest image metadata are removed; safe guest/result object
  references are placed on the garbage queue.
- Active patient AI jobs are cancelled and transient payloads cleared.
- Patient-linked `Patient`, `Analysis`, `ImageAsset`, `PatientMedia`, tooth
  status/surface and treatment records are retained rather than being deleted
  with a clinician account. They may represent a third party's clinical record
  and require a separate lawful retention/transfer policy.
- Academic materials, learning runs, chat and provider references are tombstoned
  or queued for deletion; session/reset/email challenges and trusted devices are
  removed, E2EE devices revoked, and push/realtime delivery traces removed.
- Profile/credential/membership storage paths are returned to the web caller for
  post-commit deletion.

Open privacy/operations question: patient-linked records remain attached to an
inactive pseudonymous owner and no transfer/reassignment flow is introduced by
self-erasure. This work intentionally does not delete those records or silently
reassign them. Also, the caller's profile/credential storage cleanup currently
logs a failed direct deletion; a durable retry policy for those non-AI paths
needs a separately reviewed allowlist/outbox design before changing it.

## Python security suite findings

The captured security run is no longer a pre-runner failure. It executed and
reported 50 failures / 484 passes. The failures are not one common exception:
they include direct-handler test fixture drift (e.g. raw `Query(None)` values
being bound into SQLite and handler calls missing request headers), stale
response-contract expectations, and several potentially real behavior
regressions (patient-media response serialization/receipt shape, voice receipt
key contract, admin self-erasure response, and media cleanup receipt behavior).
Only the admin self-erasure response mismatch is fixed in this change set.
The remaining Python failures are deliberately not marked fixed or green.

## Commits in this follow-up

- `6e02cbb` — transpile patient-history helper imports in the analysis-history tests.
- `f610705` — transpile the app-resume helper in retry tests.
- `2127225` — transpile the patient-directory helper in tooth-chart API tests.
- `3a1137d` — preserve the canonical web administrator exclusion in native self-erasure.
- `32d4a30` — test the administrator exclusion before and after admin step-up.
- This document records the CI evidence and remaining data-retention boundary.

The above commits were made after the CI runs listed here. Those runs therefore
validate the parent head `c21022b`, not these fixes. A fresh workflow run is
required before claiming the eight Node regressions or the Python security suite
are green. No workflow trigger was broadened and no notification-heavy automatic
CI behavior was enabled.
