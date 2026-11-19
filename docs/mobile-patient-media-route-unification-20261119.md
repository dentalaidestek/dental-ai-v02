# Native patient-media route unification — 2026-11-19

## Web flow inspected before changes

Reviewed `app/templates/patient_detail.html`, its inline gallery/upload behavior, and the web handlers in `app/main.py` before changing native navigation.

The web patient archive supports:
- PHOTO / RADIOGRAPH selection and multi-file upload (up to 12 files);
- optional FDI tooth number and a 2,000-character clinical note;
- 12 MiB per-file and 96 MiB per-batch limits;
- gallery selection, analysis of selected saved media (bounded by the analysis image limit), per-image preview/delete, and delete-all confirmation;
- authenticated patient ownership checks, streamed byte validation, actual image signature/format checks, image sanitization, and private/no-store media delivery.

The existing `NativePatientMedia` profile module already implements the mobile-safe equivalent: multi-select, encrypted local staging, durable per-file request receipts, replay/recovery, FDI and note metadata, bounded batch sizes, pagination, per-image and delete-all actions, and handoff to the native analysis uploader.

## Gap found

The root navigation still exposed a second `MediaGallery` screen backed by `ModernScreens.MediaGallery`. That duplicate was materially behind the web/profile flow: it picked only one image, uploaded directly from the picker without the encrypted durable draft/reconciliation flow, omitted FDI/note metadata and batch recovery, and did not expose delete-all. Its upload call also had drifted from the required receipt-key/batch-key API signature.

This meant the same patient-media feature had two different implementations depending on the entry route.

## Changes on `feature/mobile-web-parity-20261110`

- The standalone root `MediaGallery` route now renders the same `NativePatientMedia` component used inside the patient profile.
- The route passes authenticated `userId`, validated positive safe-integer `patientId`, and opens the existing `AnalysisResult` screen after analysis.
- The route validator rejects strings, zero, negative, fractional, non-finite, and unsafe integer IDs before mounting the archive.
- Removed the duplicate legacy gallery and its now-unused picker, upload, delete, modal and platform imports from `ModernScreens.tsx`.
- Added four regressions covering route-ID validation, root route ownership/analysis handoff, removal of the duplicate direct-upload path, and the web/native archive contract. Registered the test in `npm run test:beta`.

## Verification and limits

- `mobile/package.json` was parsed successfully after registering the test.
- Source-level GitHub checks are performed on the final head; this is not a substitute for executing the Node/TypeScript suite.
- No Actions run is associated with the current head at the time of this review. The most recent branch run inspected (run 44273348890, old code head 5b692f7) failed before any job step: `runner_id=0`, blank runner name, `steps=[]`. It did not execute npm, TypeScript or Gradle. This is an Actions runner-allocation failure signature, not evidence that source tests passed or failed.
- Full `npm test`, Android export/build, physical-device checks and the broader 60,000-user load test remain unverified.

No main merge, production deploy, migration, APK/IPA publication, or patient-record mutation was performed.
