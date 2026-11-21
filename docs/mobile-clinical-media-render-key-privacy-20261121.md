# Native clinical-media render-key privacy — 21 November 2026

## Web-first gallery and upload flow inspected

Reviewed the web implementation before changing native code:

- `app/templates/patient_detail.html`: upload limits, photo/radiograph selection, bounded gallery pages, selected-media analysis handoff, preview and deletion modal.
- `app/main.py` and `app/clinical_media_gallery.py`: owner-scoped private media, signed/cursor-bound page behavior, thumbnails, delete and upload receipt paths.
- Native comparison: `mobile/src/NativePatientMedia.tsx`, `mobile/src/clinicalMediaVault.ts`, `mobile/src/clinicalMediaRecovery.ts`, `mobile/src/clinicalMediaPresentation.ts` and `mobile/src/NativeAnalysisUpload.tsx`.

The native flow already uses encrypted device-side upload drafts, stable per-file request keys, upload receipts, bounded server paging, private image requests, selection limits and explicit recovery for ambiguous upload/delete results. These behaviors were left unchanged.

## Defect

The nested `NativeAnalysisUpload` composer used `key={owner}`, where `owner` was the raw `userId + bearer token + patientId` scope. This was a third native React-key privacy leak in the patient workflow.

The same component already creates `imageScope`, an opaque process-local identity that changes when the account, session or patient changes. Including the credential in the child key was unnecessary.

## Change

- Replaced `key={owner}` with `key={imageScope}`.
- Preserved the same remount boundary because `imageScope` is memoized against `token`, `userId` and `patientId`.
- Kept `owner` exclusively for internal request/state fencing and SecureStore ownership checks.
- Added an AST regression requiring the analysis composer key to be `imageScope` and verifying the scope rotates with the account/session/patient inputs.

No upload receipt, file hash, encrypted vault, image URL, storage object, server endpoint, patient media row, clinical note, provider request or API contract was changed.

## Validation limits

The parent-head Android CI and Security Recovery were green before these render-key changes. Latest-head runs are the authority for this new test; until those jobs start and finish, the clinical-media regression is committed but not yet reported as passed. No local checkout was available for independent test execution.

No main merge, production deployment, APK publication, migration or patient-data operation was performed.
