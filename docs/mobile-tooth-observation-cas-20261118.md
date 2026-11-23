# Tooth and surface optimistic concurrency — 2026-11-18

## Web-first findings

The web chart and patient profile were read before native changes:

- `app/templates/tooth_chart.html` selects FDI teeth and posts the status, optional surface and note to `/patients/{patient_id}/teeth/{tooth_number}`.
- `app/main.py::update_tooth_status` upserts current tooth and optional surface observations.
- Native `NativeToothChart.tsx` edits the same current-state records through the mobile API.
- Treatment records already had SHA-256 edit revisions, but tooth and surface observations did not.

## Defect

The current-state upserts are atomic and prevent duplicate rows, but upsert alone is last-write-wins. Two devices can load the same observation, then the older snapshot can overwrite a newer tooth or surface status. Unique indexes do not prevent that lost update.

## Contract added

- `app/tooth_surface_status.py::observation_revision` returns a deterministic SHA-256 fingerprint over observation kind, patient, FDI tooth, optional surface, status, note and update timestamp. The empty observation has a deterministic revision too.
- The web chart renders per-tooth and per-surface revisions into hidden form fields. A stale form returns HTTP 409; a form without a tooth revision is rejected.
- Native patient detail returns a revision beside each existing tooth and surface observation.
- Native tooth and surface mutation requests must explicitly send `expected_revision`. Explicit `null` means the observation was absent when loaded; it is not the same as an omitted field. Missing revision returns HTTP 428.
- Whole-tooth requests that also update selected surfaces must send a revision for every selected surface. A stale tooth or any stale selected surface rejects the entire transaction before upsert.
- Both mobile mutation routes lock the owning patient row with `SELECT ... FOR UPDATE` before reading and comparing revisions. This serializes observation writes for the same patient across PostgreSQL workers. Existing unique indexes and atomic upserts remain in place.
- Ownership and FDI validation still run independently of revision checks. Revision values are concurrency markers, never authorization credentials.
- Successful mutation responses return the new revision. Native then reloads the authoritative patient snapshot; it does not trust a local optimistic status as the persisted truth.

## Failure and recovery

- HTTP 409 means the chart changed elsewhere. Native keeps the current screen state and displays the conflict; the clinician refreshes the authoritative chart and reapplies the intended change.
- HTTP 428 means the client did not send a snapshot revision. Old native clients fail closed rather than silently overwriting a current observation.
- The web form similarly rejects stale/old open forms that do not contain a revision.
- Treatment creation/update receipts, treatment edit revisions, secure pending intent recovery and treatment-history cursor pagination are unchanged.
- Tooth status remains an observation, not evidence that a procedure was completed.

## Tests added

- Native API regression verifies the component passes tooth and surface revisions.
- Backend integration regression verifies first insert with explicit empty revision, successful update with the current revision, and rejection of stale tooth and surface snapshots.
- Web integration regression verifies the chart form carries a revision and stale submission returns HTTP 409.
- Existing FDI validation, owner isolation, atomic upsert, treatment idempotency and pagination tests remain in place.

## Acceptance limits

The tests are committed but were not executed in this connector session. PostgreSQL multi-worker concurrency, Android typecheck, full native beta suite, browser E2E and device-level UX remain unverified. The patient-row lock is intended to serialize PostgreSQL writes, but a real PostgreSQL concurrency run is still required before acceptance.

No production migration, main merge, live deploy, APK/IPA publication, or real-patient mutation was performed.
