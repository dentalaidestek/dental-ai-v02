# Native opaque session-scope audit — 2026-11-22

## Baseline checked before editing

Starting PR HEAD: `aa0b2645332f880fc2a6ab3dcfc3ed1ed22fa8e1`.

- Android CI run [45047215568](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/45047215568): typecheck, session/auth, realtime/pagination, beta regression suite, Android/iOS Expo exports and internal ARM64 APK build/artifact upload all completed successfully.
- Security Recovery run [45047215537](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/45047215537): Python security suite **649 passed**, PostgreSQL optimization/concurrency **29 passed**, web form/live voice browser regressions passed, and all six native security jobs passed.
- No baseline source-level Android or security failure was present. This pass therefore targeted an untested credential-retention surface rather than changing already-green CI behavior.

## Web-first trace

Before editing native code, reviewed:

- `app/templates/account.html`: profile photo/name/email/username, professional status and documents, expert profile, device notifications, password and self-erasure sections.
- `app/templates/base.html`: authenticated notification center and the dedicated `PROFILE_UPDATED` / `PROFILE_PHOTO_UPDATED` event handling.
- `app/templates/patient_detail.html` and `app/templates/tooth_chart.html`: patient-bound analysis history, FDI tooth selection and separately paged treatment history.
- `app/mobile_account_api.py` and the native account/clinical adapters to confirm the bearer token remains required only for authenticated requests.

## Finding

Four native screens duplicated the bearer token into local React state or refs used for request ownership/cache identity:

1. `NativeAccount`: a raw-token request-scope ref.
2. `NativeProfessional`: raw token in both a request-scope ref and the cached `Professional` state discriminator.
3. `NativePatientHistory`: raw token in the history data scope, active-generation ref and image-scope ref.
4. `NativeToothChart`: raw token in the patient-scope ref, selected-tooth render-identity ref and treatment-history state scope.

These values were not being sent to a new service, but duplicated credentials into additional mutable UI cache locations. The shared `useSessionRenderKey` hook already provides an opaque identity that rotates on account, token, patient and selected-tooth changes.

## Changes

- Replaced the account and professional request/cache scopes with opaque session render keys; professional cache state now stores `scopeKey`, not `token`.
- Changed patient analysis history data/generation ownership and its private image-scope discriminator to the opaque session key.
- Changed tooth-chart patient and selected-tooth/treatment-history scopes to opaque keys; removed the extra custom ref that duplicated the raw identity tuple.
- Kept the actual bearer token only in authenticated API calls and image Authorization headers. Existing stale-response rejection, patient ownership checks, FDI selection, revision/CAS writes, draft recovery and web-compatible navigation remain intact.
- Updated the patient-history and tooth-chart VM harnesses to load the real production hook rather than a placeholder/pure helper.
- Added source-level regressions covering all four screens and the two hook-enabled VM harnesses.

## Validation boundary

The changes are committed on `feature/mobile-web-parity-20261110`. The baseline runs above validate only `aa0b264), not these new commits. The final-head Android typecheck/beta suite and Security Recovery must complete before the new scope regressions are reported as passing. No local full-repository test or physical-device test is claimed.

No merge to `main`, live deployment, migration, account mutation or patient-data operation was performed. The 60,000-user load test remains a separate acceptance gate.


## Second pass: AI analysis and viewer lifecycle

A second web-first trace covered:

- `analysis_new.html`: existing clinical-media selection, the four-image cap and byte-budgeted upload form.
- `analysis_viewer.html`: modality-specific viewer selection, same-origin iframe messaging, asset/vision URLs, manual finding and clinical-note saves, and retryable job recovery.
- `result.html`: final clinical result sections, findings, treatment options and cautions.
- `app/mobile_analysis_api.py`: patient-scoped upload receipts, private analysis access and bounded mobile result/workspace responses.

The corresponding native flow is `NativeDentalAI` → `NativeClinicalReview` → `NativeVisionViewer`.

This pass found three additional credential-retention surfaces:

- `NativeDentalAI` kept the token in its custom render-session ref, request-scope ref and previous-search scope ref.
- `NativeClinicalReview` kept the token beside the viewer remount key.
- `NativeVisionViewer` kept the token in both the private image-scope ref and the latest-request ref.

These did not replace server authorization, but unnecessarily duplicated a bearer credential in long-lived UI refs. They now use the shared opaque session key. Vision requests still send the current render's token to the authenticated API call; stale responses compare only opaque session identity plus analysis/asset/modality. No polling interval, AI request count, image retry cost or server workload was increased.

The VM harnesses for AI recovery, clinical review and vision viewer now load the production hook (or a hook adapter backed by the same production identity resolver for the custom fake-React harness). Additional static regressions cover all three screens and their harness mappings.


## CI regression found during this pass

The first Security Recovery after the AI-viewer changes exposed one test-harness omission, not a production-code failure: `patientHistoryRetry.cjs` instantiated `NativePatientHistory` but its VM import map did not provide the newly required `./useSessionRenderKey` hook. The failing test reported `Unexpected import ./useSessionRenderKey`. The other native security jobs in that run completed successfully; the clinical aggregate was red because this one test process exited non-zero.

Fixed the retry harness to load the production hook and added a guard in `sessionRenderKey.cjs` so the retry harness mapping cannot silently regress. A fresh Android CI and Security Recovery were queued for the new HEAD after that fix; until those runs complete, the newly changed tests are **not** claimed as passing.
