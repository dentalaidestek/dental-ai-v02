# Mobile vision viewer retry-race follow-up — 2026-11-22

Branch: `feature/mobile-web-parity-20261110`  
PR: #257 (draft) · Issue: #258

## Web-first flow inspected

Before native edits, reviewed:

- `app/templates/patient_detail.html`: clinical archive, saved-media selection, four-image analysis handoff, history and patient return.
- `app/templates/analysis_new.html`: saved + new image composition, FDI/clinical note fields, per-file and aggregate byte limits.
- `app/templates/analysis_viewer.html`: modality-aware viewer boot, asset switching, same-origin postMessage contract, manual finding/note persistence, treatment-analysis start/result and retry handoff.
- `app/main.py`: owned viewer note/finding/treatment handlers and private asset/vision routes.
- `app/mobile_analysis_api.py`: patient ownership, saved-media ownership, request-key receipt and bounded image validation.
- Native counterparts: `NativePatientMedia`, `NativeAnalysisUpload`, `NativeClinicalReview`, `NativeVisionViewer`, `analysisUpload`, `clinicalApi`.

## CI root cause at starting HEAD

Starting PR HEAD: `04fef66a7386b10e41d7f2d8d9bc66a57f51b9a6`.

- Android run #4893: TypeScript typecheck passed; session/auth and realtime/pagination tests passed; APK job and Android/iOS Expo exports passed. The aggregate job failed only in `npm run test:beta`: 1,028 passed / 1 failed.
- The only failure was `mobile/tests/sessionRenderKey.cjs:143-157`. Its assertion still expected the deleted ad-hoc `useMemo(() => 'clinical-media-scope-...')` implementation. Production had correctly moved to the shared `useSessionRenderKey` hook and `imageScope=owner`. This was a stale test contract, not a typecheck or production source failure.
- Security Recovery #2592 passed all seven jobs. The Python security/identity, PostgreSQL migration/concurrency and web form/live voice checks completed successfully; all six native security jobs passed.

## Native issue found and fixed

In `NativeVisionViewer`, the image's `onLoad` and `onError` callbacks previously checked token, analysis, asset and modality. Those checks did not distinguish two image revisions for the same asset.

When a clinician pressed “Görüntüyü Yeniden Yükle”, an event from the previous image request could still arrive afterward. A late error could incorrectly mark the new image as failed; a late load could supply dimensions from the old image to the new overlay.

The viewer now tracks the current opaque `imageKey` in a ref and accepts image callbacks only when the captured key still matches. The error callback also checks that the viewer remains mounted. This does not create a second AI job or repeat the vision request.

Regressions cover:
- a previous revision's delayed `onError` cannot poison a retry;
- the current revision's own `onError` remains visible;
- a previous revision's delayed `onLoad` cannot restore stale SVG overlay dimensions;
- the current revision's dimensions are accepted.

## Commits in this follow-up

- `6a766a7` — update the stale media session-scope assertion to the shared hook contract.
- `f2be83d` — ignore stale clinical image load/error events after a retry revision.
- `f520396` — cover stale image errors after retry.
- `7d5ede7` — cover stale image dimensions after retry.
- This document records the web-first review and CI evidence.

## Acceptance still open

The five commits above are on the feature branch only. CI must run again against the final HEAD before the new regression tests can be called passing. No physical Android/iOS image viewer test, real R2 image retry, main merge, production deploy, migration or patient-data operation was performed. The 60,000-user goal is not load-tested or capacity-certified by these changes.
