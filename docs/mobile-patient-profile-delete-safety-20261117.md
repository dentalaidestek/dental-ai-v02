# Native patient profile mutation and deletion safety — 17 November 2026

PR #257 / issue #258. Web reference was read before changes from the PR base branch `feature/mobile-beta-20261110`:
- `app/templates/patient_detail.html`: patient summary, quick actions, collapsed identity edit form, two-stage delete confirmation, clinical archive, analysis history and treatment history.
- `app/main.py`: `edit_patient` normalizes the editable fields and emits PATIENT_UPDATED; `delete_patient` checks ownership and removes the patient/profile.
- The native profile was compared at `mobile/src/NativePatientProfile.tsx`, with optimistic edit revision and SecureStore-backed treatment mutation intent.

## Defect found

The native screen showed the web-equivalent destructive delete action even while a local treatment mutation intent was still being restored, unreadable, or awaiting receipt reconciliation. It also allowed an ambiguous patient edit (timeout/5xx) to be cleared by a manual “Kontrol ettim” acknowledgement after starting a fire-and-forget refresh. That acknowledgement did not prove the server state had been read successfully or matched the draft.

This was a native-only lifecycle gap. The backend already has two independent protections:
- Patient edit uses a row-locked, owner-scoped edit revision and returns 409 for stale snapshots.
- Patient deletion is owner-scoped and returns 409 when dependent clinical records exist; the native adapter deliberately does not cascade-delete clinical history.

## Changes

1. Added `patientProfileEditMatches`, which compares all seven web-editable fields (first/last name, phone, birth date, TC number, address and chief complaint) using the backend's trim/null normalization.
2. Replaced the manual uncertainty acknowledgement with an explicit authenticated profile read. A matching read confirms the previous write; a mismatch preserves the draft, refreshes the revision and permits an explicit resubmission. A failed read keeps the uncertain state locked.
3. Added a fail-closed delete gate. Deletion is unavailable while the profile is busy/uncertain, while treatment-intent restore is incomplete, when the secure intent is corrupt, or while a treatment create/update receipt is unresolved.
4. The second destructive confirmation rechecks the live gate, not only the state captured when the first alert opened.
5. Added React renderer regressions for normalization, pending/corrupt SecureStore intents, ambiguous edit reconciliation success/failure, and the gate predicate.
6. Added backend regressions for owner-scoped patient deletion, 409 when clinical dependencies exist, and successful deletion only for an owned patient with no dependent clinical rows. Added a security source invariant so the native gate is included in the existing patient-parity security workflow.

## Validation and limitations

- The pure presentation helper was checked independently with Node 22 and the globally installed TypeScript transpiler.
- The full React renderer test file requires the mobile dependency set (React 19 / react-test-renderer / TypeScript 5.9.2); those packages are not installed in this execution environment, so the new renderer tests are committed but not run here.
- The Python API tests are committed but not run here.
- At starting HEAD `364062f8964bc987aaf5d94da7742c92af14c917`, Android typecheck and APK jobs plus Security recovery had completed failure with `steps=[]`; direct step queries returned empty arrays and typecheck log download returned BlobNotFound 404. No compiler, Gradle or pytest step ran. The exact GitHub runner allocation/account cause is not exposed.
- Real two-account Android/iOS confirmation, screen-reader and destructive-dialog device checks, and the full mobile/Python suites remain open.

No patient record was changed by this work. No main merge, live deployment or store publication.

## Follow-up hardening: independent mutation lifecycles

Reviewing the new guard exposed a second-order race: the screen previously reused one `uncertain` boolean for both patient-profile edits and treatment receipts. A restored treatment intent could coexist with a profile form, and a successful treatment receipt could clear the shared flag even if a profile edit was still uncertain.

Separated the state into `profileUncertain` and `treatmentUncertain`. Patient edits now wait for treatment-intent restoration and are blocked while a treatment intent is pending; treatment writes are blocked while a profile edit is uncertain. A treatment receipt can no longer resolve a profile mutation, or vice versa. The delete gate consumes the union of both states plus the pending/blocked SecureStore flags.

A second destructive-alert review found that the nested native confirmation could outlive the screen/account scope. Both the initial and final delete callbacks now require the original patient/account scope to remain current. The final confirmation still rechecks the live mutation gate.

Additional renderer regressions cover pending-treatment/profile-edit isolation, profile uncertainty preventing treatment writes, and discarding a second delete confirmation after account/patient switch. The Python source invariant now checks both uncertainty states and both stale-scope guards. These new tests are committed; full React renderer and Python execution remain blocked by unavailable package/runtime and GitHub runner execution.

A final lifecycle pass added focus awareness to the destructive dialog. Both confirmation callbacks now require the original patient/account scope and the profile screen to remain focused; navigating to another patient/account or blurring the profile discards the pending confirmation. Renderer coverage was added for blur as well as account/patient switch.

Patient identity isolation: the initial profile load, stale-revision reload, and ambiguous-edit reconciliation now all verify that the returned `patient.id` equals the requested route ID before rendering or clearing uncertainty. A mismatched response is rejected; reconciliation remains locked and deletion stays disabled. Added renderer cases for both initial load and uncertain-edit reconciliation.
