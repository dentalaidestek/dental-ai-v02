# Mobile Program cursor integrity — 2026-11-19

## Web flow reviewed

The canonical web flow was re-read in app/templates/program.html, app/templates/program_form.html, app/main.py (program_page, create/edit/copy/complete/delete, _validate_schedule_input, reminder queue helpers), and the native adapter app/mobile_program_api.py. Native rendering remains a 50-item selected-day page over the shared Istanbul wall-time and recurrence engine.

## Defect and impact

The prior cursor was base64-encoded JSON with a deterministic user-ID tag. The query itself was owner-scoped, so this did not expose another user's events. But the cursor was not authenticated: a client could alter the page watermark, last occurrence timestamp or tie-break ID, causing records to be skipped or repeated while continuing to read only its own events.

## Fix

- Cursor format advanced to version 2.
- Canonical JSON is authenticated with HMAC-SHA256; the 32-byte signature is appended before base64url encoding.
- The MAC key is domain-separated from the authenticated opaque bearer session token.
- GET /api/mobile/v1/program obtains the token through _mobile_access_token and uses it for both cursor generation and verification.
- No token, patient identifier or appointment content is added to cursor storage.
- A changed signature, another session token, wrong account/view/day or invalid structure returns 422. A cursor older than 15 minutes remains 410. A schedule mutation detected after the first page remains 409 and requires a fresh first-page request.
- Calendar responses retain Cache-Control: private, no-store, Pragma: no-cache, and Vary: Authorization.

The cursor is short-lived and session-bound. It is a tamper-evident pagination watermark, not a durable cross-session snapshot or a database MVCC snapshot.

## Regression coverage added

- tests/test_mobile_program_api.py: key derivation/domain separation, Istanbul wall-time round-trip, account mismatch, session-token rotation, payload tampering, expired and future watermark rejection.
- tests/test_mobile_program_parity.py: 51-row pagination produces a cursor, verifies private cache headers and rejects a modified signature at the authenticated endpoint.
- Existing native UI behavior still exposes a first-page refresh after a cursor error; no polling or new workflow was added.

## Verification boundary

The latest branch HEAD before this follow-up had no associated GitHub check runs or commit status entries. The most recent inspected APK job had an empty step list; its log artifact returned BlobNotFound, so no TypeScript, Gradle or security test ran. This follow-up did not dispatch CI. The new pytest cases are committed but not executed here; full pytest, Android tsc --noEmit, native component tests, APK build, device acceptance and 60,000-user load tests remain open.

No main merge, production deploy, migration, dependency change or patient record mutation.
