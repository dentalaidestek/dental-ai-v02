# Native Program mutation idempotency — 2026-11-17

## Web flow reviewed first

The web Program flow remains canonical for validation and reminder behavior:

- `app/templates/program.html` and `app/templates/program_form.html`
- `app/main.py`: `_validate_schedule_input`, `_sync_program_reminder`, `_record_program_realtime_event`, and the web create/edit/delete/copy handlers
- `app/mobile_program_api.py`: native range, conflict, create, edit, copy, complete and delete routes
- `mobile/src/NativeProgram.tsx`, `NativeProgramEditor.tsx`, `programApi.ts`, and `programModel.ts`

The native editor already reused the web validator and reminder worker. The missing parity contract was recovery after an ambiguous create response.

## Newly found defect

A native create request could commit the ScheduleEvent, reminder job and realtime event while the mobile connection failed before the response reached the device. The editor then had no durable server key to reconcile the result. A later tap or process restart could create another appointment and another reminder.

This was a data-integrity issue, not merely a duplicate-button issue.

## Changes

### Server

- Added nullable `client_request_hash` and `client_payload_hash` fields to `ScheduleEvent`.
- Added one unique composite index on `(owner_user_id, client_request_hash)`. Web-created events keep both fields NULL.
- Added request-key validation and keyed payload fingerprinting in the native schedule-create path.
- The request key is random and account-scoped; the database stores only SHA-256/HMAC fingerprints, not the raw key, appointment title, notes or patient ID.
- Event creation, reminder enqueue, durable notification creation, realtime event and receipt fingerprint flush in the same savepoint/transaction.
- A unique-index race rolls back the losing transaction's event and side effects, then returns the winning event only if the payload fingerprint matches.
- Reusing a key with different content returns 409. Replaying a key for a soft-deleted event returns 410 rather than recreating it.
- Added `GET /api/mobile/v1/program/mutations/{request_key}` for owner-scoped recovery. It returns only NOT_FOUND, FOUND or DELETED; a foreign owner's key hashes to a different value.

### Database release migration

- Schema revision is now 15.
- Revision 14 → 15 adds the two nullable columns and the unique index under a transaction-scoped advisory lock.
- Older supported migration paths still advance through revision 14 before the Program migration.
- `main.init_db()` also adds the columns/index for fresh and legacy SQLite/PostgreSQL initialization.
- Production rollout must run `python -m app.migrate` before starting code that requires schema revision 15. This branch has not been deployed.

### Native

- Added `mobile/src/programIntent.ts`.
- SecureStore keeps only the random request key, scoped to the authenticated account. It does not persist patient IDs, titles, notes, tokens or appointment payloads.
- A pending key is shared across the Program tab and patient-profile appointment entry point, so changing entry points cannot bypass recovery.
- The editor checks the server receipt on reopen. FOUND reconciles the existing event; DELETED clears the resolved key; NOT_FOUND retains the key for a safe same-key retry.
- If local key persistence or cleanup is uncertain, submission stays blocked rather than generating a replacement key.
- `programApi.ts` now sends the request key for creates and validates receipt states.

## Regression coverage added

- Native request-key storage, account isolation, process-death reuse, corrupt-key fail-closed behavior and compare-before-clear.
- Native API request-key submission and receipt lookup.
- Backend replay returns the same event and does not create another reminder.
- Same key with changed payload returns 409.
- Foreign-account lookup returns NOT_FOUND.
- A deleted event's key remains a tombstone and returns 410.
- PostgreSQL migration from revision 14 to 15.
- PostgreSQL two-worker create race expects one event, one reminder and one replay response.
- Existing Program lifecycle, recurrence, owner-scope, conflict-advice and 50-item pagination tests remain in place.

## Still open

- The full Android typecheck, beta suite, Python pytest, PostgreSQL integration suite and APK build have not been confirmed by GitHub Actions because the recent workflow jobs were created without runner steps and their log artifacts returned 404. Isolated source/logic checks are not a substitute for these runs.
- Native Program now uses a versioned base64url continuation cursor bound to the authenticated owner, view and selected day. It carries a 15-minute UTC snapshot watermark and the last `(start_local, event_id)` tuple, giving equal-time appointments and weekly occurrences a deterministic continuation order.
- The occurrence helper filters rows by `created_at` and `updated_at` at that watermark. Before and after a cursor-page read, the API checks for owner schedule writes newer than the watermark; it returns 409 and asks the client to refresh rather than silently mixing a changed calendar into an old page. Legacy numeric offset remains available for older installed clients.
- This is stable transfer pagination, not yet a database-level occurrence query: the helper still loads and expands the selected user's events in the requested date window to calculate day counts and weekly occurrences. A 60,000-user load certification and query-plan measurement remain open.
- Native OS push scheduling and killed-app deep links remain incomplete; in-app Program reminders and notifications are not evidence that Expo push is live.
- No 60,000-user load certification was run.
- No main merge, production migration, deploy or APK/IPA publication was performed.


## 2026-11-17 — Stable native Program continuation

- Re-read the web Program page/form and canonical `_user_schedule_occurrences` / `_event_occurrences` helpers before changing the native range contract.
- Native Program continuation now uses a versioned base64url cursor with owner scope, view/day scope, a 15-minute UTC snapshot watermark and the last `(start_local, event_id)` ordering key. Equal-time events and repeated weekly occurrences no longer depend on a shifting numeric offset.
- A new event or an edit/completion/deletion after page one invalidates later pages with HTTP 409. The native list asks for a full refresh instead of appending a mixed calendar snapshot. Cursors expire after 15 minutes and are rejected when reused for another owner/view/day.
- Legacy offset requests remain supported for older native builds. No database migration or new index was introduced.
- Backend and native regressions cover 120 equal-time records, complete/no-duplicate traversal, cursor scope validation, invalid cursors, create/update invalidation and old-backend offset fallback.
- Android workflow path filters now include `app/mobile_program_api.py`, so native API contract changes trigger typecheck/beta validation.
- Full Python/Node/TypeScript/Gradle execution remains gated by GitHub Actions runner allocation; static source checks are not represented as full-suite passes.
