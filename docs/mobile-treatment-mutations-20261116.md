# Native treatment mutation safety — 2026-11-16

## Web-first contract review

The current web patient flow was reviewed before changing native behavior:

- `app/templates/patient_detail.html` renders treatment history.
- `app/templates/treatment_new.html` posts a new treatment to `/patients/{patient_id}/treatment/new`.
- `app/main.py` owns the web creation handler.
- The reviewed web flow has no treatment edit or delete action. No delete endpoint or destructive native control was invented in this change.
- Native already exposes treatment editing, so its update path now has an optimistic revision check.

## Backend contract

The mobile create and update routes accept a client `request_key` (16–80 URL-safe characters). The server hashes the key together with the authenticated user, patient, operation, and treatment ID. The raw key is not stored.

A receipt is stored in the existing `WorkJob` table with:

- `kind=TREATMENT_RECEIPT`
- `resource_type=PATIENT` and `resource_id=patient_id`
- `status=DONE`
- a SHA-256 hash of the normalized mutation payload
- a small JSON result containing only patient/treatment IDs, operation and revision

PostgreSQL requests take a transaction-scoped advisory lock for the receipt key before lookup and insert. Repeating the same key and payload returns the original treatment ID and revision. Reusing a key with different data returns HTTP 409. The receipt is retained while its patient exists, so the 30-day work-history pruner cannot reopen an old create retry and create a duplicate.

Treatment edit revisions are SHA-256 fingerprints over the treatment ID, patient ID and editable clinical fields. Native sends the revision it read. A stale update returns HTTP 409 and does not overwrite the newer treatment. This revision is a concurrency marker, not an authorization token; patient ownership checks remain mandatory.

## Native recovery

Before sending a create/update request, the native screen stores the exact intent in the existing chunked SecureStore wrapper. The storage key is scoped to both user and patient:

`dai.treatment.<user_id>.<patient_id>`

The stored intent contains the request key, operation, treatment ID/revision and normalized form payload. While an intent is pending, its fields are locked. An uncertain network response keeps the encrypted intent. After a screen/app restart, the clinician can replay the exact same request; the server receipt makes that retry idempotent. A successful, validated receipt clears the local intent.

A malformed or unreadable saved intent blocks new treatment writes rather than silently dropping a potentially committed request. The app must not switch the pending intent to a different user or patient.

## Validation added

- Backend: create replay, changed-payload key reuse, ownership isolation, update replay, stale revision rejection, malformed revision rejection, receipt retention.
- Native API: stable request key and expected revision are sent; malformed receipt responses are rejected.
- Native intent: account/patient scope, request key, treatment ID, revision, FDI tooth, Gregorian date and field-size validation.
- Native UI: secure intent is persisted before network mutation and survives remount; retry uses the same request key.

## Remaining scope

- The web treatment form still does not expose edit/delete controls; parity for those actions requires a separate web UI/route change.
- No treatment delete endpoint was added because the inspected web flow does not provide one.
- Repository pytest, full native beta suite, Android typecheck and APK build still require a functioning GitHub Actions runner. Do not interpret an empty job step list as a test pass.
- No main merge, production deploy or real-patient mutation is part of this work.
