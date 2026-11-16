# Native Academic AI run cancellation — 2026-11-16

## Web-first comparison

Read the current web implementation added in the Academic AI web update:
- `app/templates/notes_ai.html`: `addRunCancel` adds “Bu işlemi durdur” to the currently active durable run and clears the web polling timer after the canonical response.
- `app/main.py`: `POST /notes/courses/{course_id}/ai/runs/{run_id}/cancel` authenticates the user, verifies course ownership, and delegates to `academic_study_runs.cancel_run`.
- `app/academic_study_runs.py`: cancellation locks the exact (run, owner, course) row and changes only QUEUED/RUNNING/INTERRUPTED rows to CANCELLED. Terminal rows are returned unchanged. The normal completion transaction requires status RUNNING, so a cancelled run cannot subsequently commit its answer.

The native Academic AI screen previously polled a durable run and prevented duplicate generation, but had no matching cancellation action.

## Native adaptation

- Added authenticated `POST /api/mobile/v1/academic/courses/{course_id}/runs/{run_id}/cancel` and delegated to the canonical web handler. No second cancellation policy or provider path was introduced.
- Added a validated client helper. Course and run IDs must be positive safe integers; the response must match the existing durable-run contract.
- Added “Bu işlemi durdur” only while the current course run is QUEUED/RUNNING. The control is disabled while the request is pending and the screen shows the canonical CANCELLED state/error only after a server response.
- On an uncertain cancellation response, the client reads the canonical run status before leaving the current state unresolved; repeated cancel remains safe.
- Added a run-version guard so a previously-started status poll cannot overwrite a newer cancellation response.
- Backend regressions cover owner isolation, cross-course isolation, idempotent repeated cancellation, private/no-store response and preservation of the queued run after unauthorized attempts. Native regressions cover endpoint shape, active-run UI, canonical result and stale-poll race.

## Cancellation boundary

This mirrors the current web behavior. The durable run is marked CANCELLED and the completion transaction refuses to commit a later answer. This does **not** prove that an already-running upstream model/provider request is physically interrupted at the moment the button is pressed; provider-level cooperative cancellation is a separate capability and is not claimed here.

## Validation and remaining acceptance

The new backend and Node regression cases are committed and included in the existing security and `test:beta` workflow paths. They have not been executed in this connector-only session. Current GitHub Actions on the previous code head had failed before any step; typecheck/pytest results must be taken only from a new provisioned run. Physical Android/iOS acceptance, two-account production API validation, provider cancellation semantics, and full 60,000-user capacity tests remain open.

No main merge, production deployment, APK/IPA publication or live account/course mutation was performed.
