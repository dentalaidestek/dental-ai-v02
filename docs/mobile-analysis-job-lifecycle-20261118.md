# Native AI analysis job lifecycle and polling — 2026-11-18

## Web flow checked before native changes

Reviewed the authenticated web flow first:

- `app/templates/analysis_new.html`: patient context, FDI tooth number, clinical notes, up to four selected gallery/new images, per-file and batch byte limits.
- `app/templates/analysis_viewer.html`: authenticated viewer bootstrap and retry hand-off.
- `vision_service/templates/radiograph_viewer.js` and `intraoral_viewer.js`: authenticated image/vision reads and bounded pending-result wait (up to 40 attempts, exponential delay capped at 15 seconds, plus jitter).
- `app/mobile_analysis_api.py`: image-backed uploads enqueue `VISION`; context-only uploads enqueue `PRELIMINARY`; analysis detail returns the latest `WorkJob`.
- `app/main.py`: `_enqueue_work` marks image work `VISION_PENDING`; successful vision becomes `VISION_READY`, unavailable vision becomes `VISION_ERROR`; preliminary/final publication uses `AI_ANALYZED` / `AI_FINAL`.
- `app/mobile_clinical_api.py`: the authenticated, owner-scoped job action already supports retry/cancel for `VISION`, `PRELIMINARY` and `FINAL`.

## Newly found parity defects

1. The mobile analysis-detail validator allowed only `PRELIMINARY` and `FINAL` job kinds, while the backend correctly returned `VISION` immediately after an image-backed upload. `NativeAnalysisUpload` then called `NativeDentalAI.openUploaded → getAnalysis`; the valid server response was rejected as a 502 before the just-created analysis could be opened. This was a client/server contract mismatch, not a missing backend job.
2. The parent analysis screen polled every 15 seconds even after the image job reached `VISION_READY` or `VISION_ERROR`. Those states were omitted from its stop list. A completed image stage therefore continued generating status reads while the clinician was deciding whether to start the preliminary clinical AI step. A failed/cancelled work job could also leave the parent polling despite the clinical screen already exposing its retry action.

## Changes

- `MobileAnalysisJob.kind` and its strict response validator now accept the canonical `VISION` kind while still rejecting unknown kinds and extra fields.
- Added `analysisRefresh.ts` as a pure lifecycle policy:
  - stop at `VISION_READY`, `VISION_ERROR`, `AI_ANALYZED`, `AI_FINAL` and other terminal analysis states;
  - stop when the latest work job is `DONE`, `FAILED` or `CANCELLED`;
  - use 15s → 30s → 60s fallback delays with bounded ±10% jitter;
  - cap one automatic refresh sequence at 40 attempts;
  - retry transport/5xx/429 failures with backoff, but stop immediately on authentication, ownership, missing-resource, conflict or validation errors;
  - stale responses invalidated by a newer foreground/realtime/manual read cannot schedule another timer.
- `NativeDentalAI` now uses a one-shot timeout rather than a fixed 15-second interval. Foreground return, matching analysis realtime events and the manual “Sonucu Yenile” action restart the bounded sequence. Background state does not keep a timer loop alive.
- Existing owner checks, patient/analysis ID matching, account-scope guards, durable upload receipt, encrypted local image intent and clinician approval rules remain unchanged. No provider, prompt, clinical taxonomy, endpoint, database schema or production setting changed.

## Regression coverage

- `mobile/tests/analysisApi.cjs`: accepts a synthetic image-backed `VISION/QUEUED` envelope and rejects unknown job kinds.
- `mobile/tests/analysisRefresh.cjs`: terminal analysis/job states, 15/30/60-second backoff, jitter bounds, 40-attempt cap, permanent-vs-transient error handling, stale-response guard and absence of the old fixed interval.
- Both test files were already included in `npm run test:beta` / `npm run test:realtime`; no new workflow or CI trigger was added.

## Verification and remaining limits

- GitHub source inspection confirmed the web/backend/native status and job-kind contract described above.
- The exact `analysisRefresh.ts` policy was compiled with `tsc --noEmit --strict --target es2020` against a minimal type-only `MobileAnalysis` declaration: passed. An isolated Node run executed 13 lifecycle/terminal-state assertions and 7 backoff/jitter/attempt-cap assertions: all passed.
- The committed `analysisApi.cjs` and `analysisRefresh.cjs` suites were not run as repository test files. Full repository `npm run typecheck`, `npm run test:beta`, `npm run test:realtime`, pytest, Expo export and Gradle were not run in this connector-only workspace.
- At starting HEAD `b78bd8523df165b276fc4572897038e6124e42c5`, GitHub returned no PR workflow runs and no combined status entries. The last documented older-head Android/Security runs failed before steps (`runner_id=0`, empty steps, `BlobNotFound 404`); compiler, Gradle and pytest did not start. This does not establish a source-level TypeScript failure or a passing CI result. The exact hosted-runner/account/billing cause remains unavailable from the returned GitHub records.

No main merge, production deploy, migration, APK/IPA publication or clinical-record mutation was performed.
