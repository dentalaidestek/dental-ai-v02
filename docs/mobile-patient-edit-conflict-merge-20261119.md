# Native patient edit conflict merge — 2026-11-19

## Web flow reviewed first

Before the native change, the following web paths were re-read:

- `app/templates/patient_detail.html`: the patient-information form submits `expected_revision` with the editable identity/contact/address/complaint fields.
- `app/main.py::edit_patient`: the PostgreSQL path locks the patient row, recomputes the canonical revision, and returns HTTP 409 when another session changed the profile.
- `app/mobile_api.py::mobile_patient_detail`: the native profile payload includes the same edit revision and the editable profile fields.
- `mobile/src/NativePatientProfile.tsx` and `mobile/src/api.ts::editPatient`: the native form uses that revision on its PUT mutation.

The web endpoint's optimistic concurrency check is the source of truth; no server contract or revision calculation was changed.

## Newly found native-only data-loss/overwrite paths

1. After a 409, the native “reload current patient” action replaced the entire form with server values. Unsaved fields from the clinician's draft disappeared.
2. A realtime/app-resume refresh could update the in-memory profile revision while the edit form remained open. The next save could then submit an older form against the newer revision and silently overwrite another session's edits without receiving a 409.

## Changes

- Added `patientProfileMergeEditConflict` to `mobile/src/patientProfilePresentation.ts`.
- Three-way merge compares the form's base snapshot, local draft and latest server snapshot.
- Fields unchanged locally adopt the latest server value.
- Local-only changes remain in the draft.
- If both sessions changed the same field differently, the field is shown as a conflict with explicit “Taslağımı koru” and “Güncel değeri kullan” choices.
- Save remains disabled until every same-field conflict is resolved.
- A refresh while a dirty profile draft is open keeps the prior edit revision and patient snapshot, surfaces the conflict action, and does not silently advance the revision.
- The latest revision is adopted only after the clinician explicitly merges/reviews the current profile.

Editable fields covered: first name, last name, phone, birth date, Turkish identity number, address and chief complaint.

## Privacy and compatibility

- Owner-scoped mobile patient detail and edit authorization are unchanged.
- Existing `private, no-store` behavior is unchanged.
- No TC number is added to list/search results.
- No clinical history is inferred or automatically written from voice/AI output.
- No new API endpoint, database query, schema, migration, polling loop or background job was added.
- Conflict values are rendered only in the active clinician's native form; they are not logged or sent to analytics.
- No patient record was mutated by this code-only change.

## Regression coverage added

`mobile/tests/patientProfileUI.cjs` now covers:

- three-way merge of unrelated remote/local field changes;
- explicit same-field conflict choices;
- save blocking while a conflict remains;
- retry using the refreshed edit revision;
- preserving remote-only phone/address updates;
- a realtime refresh while the native form is open, proving that the old revision is not silently replaced.

The file is already included in `npm run test:beta`.

## Verification status

The source and test changes were committed to `feature/mobile-web-parity-20261110`. The new React Native renderer tests, complete `npm run test:beta`, Android `npm run typecheck`, Python Security Recovery, Expo export, Gradle build and physical-device flow have not been executed in this connector-only run. Do not interpret committed tests as passing CI.

At the starting HEAD `817a879`, combined status and PR-associated workflow runs were empty. The PR description contains current-head Actions evidence from 2026-11-16: Android typecheck/APK and Python security jobs failed before any step, with runner ID 0 and `BlobNotFound 404` log downloads. This does not establish a source-level TypeScript or pytest failure; the exact hosted-runner/account/billing sub-cause remains unavailable.

No main merge, live deploy, production migration, APK/IPA publication or clinical data mutation.
