# Mobile Program receipt integrity — 2026-11-21

## Web-first flow inspected

Before changing native Program behavior, compared:

- `app/templates/program.html`: today/week/month navigation, day/month grid, event actions, copy-to-days sheet, duplicate-submit lock and realtime refresh.
- `app/templates/program_form.html`: event types, patient association, start/end wall time, reminders, weekly recurrence, recurrence end, location and notes.
- `mobile/src/NativeProgram.tsx`: native calendar, cursor pagination, account-scoped pending action intent, copy/complete/delete and realtime refresh.
- `mobile/src/NativeProgramEditor.tsx`: common appointment/program editor, conflict advisory, request-key recovery and edit reconciliation.
- `mobile/src/programApi.ts`: mobile Program page, event, mutation receipt and write contracts.

The native screen already covered the main web interactions. The gap was not a missing button: it was the strength of the server receipt contract.

## Finding

The mobile save response previously checked only the returned event ID (for edits), start time and patient ID. A response with the same start/patient but a different title, end time, location, notes, reminder or recurrence could still be accepted and close the editor.

The create-recovery path had a related problem: after a timeout, a `FOUND` mutation receipt was accepted without comparing it to the form payload still held in memory. That could make a mismatched receipt appear to be the just-submitted appointment.

## Changes

- Added one complete event/payload comparator in `programApi.ts`.
- Apply the comparator to both create and edit write receipts.
- When an in-memory create payload exists, keep a mismatched `FOUND` receipt unresolved and retain its SecureStore request key. Do not clear the key or navigate to the receipt.
- After process restart, when the payload intentionally is not persisted, the server's account-bound idempotency key remains the authoritative recovery proof; appointment titles, patient IDs and notes are not copied into local request-key storage.
- Normalize nullable end-time and recurrence-end fields at the editor boundary.
- Validate event status/type, wall-clock ordering, reminder/recurrence values, bounded patient/location/note fields, calendar row identifiers and page date/cursor metadata before rendering.

## Regression coverage

Added synthetic-only tests for mismatched title, end time, patient, location, notes, reminder and recurrence. Added malformed event tests for reversed times, object-valued patient names, oversized location/notes and impossible recurrence dates. Added a rendered editor recovery test asserting that a mismatched `FOUND` receipt neither clears the request key nor calls the saved callback.

## Boundaries

No database schema, backend route, reminder queue, provider, dependency, production patient record or notification token was changed. No main merge, deployment, migration, APK/IPA publication or live-device test was performed.

The code and tests are committed to `feature/mobile-web-parity-20261110`. Android typecheck, beta tests and Security Recovery must pass on the resulting HEAD before this work is considered verified.
