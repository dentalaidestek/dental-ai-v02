# Program / native calendar adaptation

Continues PR #257 / issue #258 on `feature/mobile-web-parity-20261110`, based on `209575dfb9bd144ed6297fd6417a4c1b0d22ca44`. Concurrent patient mutation-scope code/tests are retained. No main merge, production deploy or store publication.

## Confirmed defects

- Legacy mobile schedule creation called the shared validator but omitted `_sync_program_reminder` and the worker wake-up. An accepted native appointment therefore did not enqueue the same reminder as the web creator.
- The boolean notification choice was passed to a validator whose authoritative input is the reminder selection. Passing a numeric reminder with notification disabled could still enable it. Native creation now passes `NONE` for the disabled case and preserves the web queue/notification resolution/event publication flow.
- The old list selected the first 100 event anchors ordered by start time. Historical records could hide future entries, and weekly anchors were not expanded into their actual calendar occurrences.
- General Program was a plain title/start text form with no edit/copy/weekly/end/reminder-off controls. The separate patient appointment form also lacked the full web form options.

## Web-to-native flow mapping

| Web behavior | Native source implementation |
|---|---|
| Today / week / month | `NativeProgram`, shared `_program_range`, `_program_week_days` and `_user_schedule_occurrences`; same rolling seven-day week and 42-day month grid |
| Previous/next/date selection | Server-provided calendar dates, counts and Turkish month title; owned selected-day records in virtualized pages of 50 |
| Event types / title | All current web event types; top add and week empty-state Class shortcut |
| Start / end | Native date and exact hour/minute selectors; no raw datetime typing; Turkey wall times converted/stored through the existing web validator |
| Patient | Real owned patient selection with search/pagination; verified initial patient from its profile; clear stale patient linkage for nonclinical event types |
| Reminder | All existing options, including NONE, at-time, 15/30/60/120 minutes and one day; actual reminder queue synchronization |
| Advanced fields | Location, notes, weekly recurrence and optional recurrence-until date |
| Edit | Original owned event/weekly anchor loaded; invokes the web edit handler and its reminder/realtime behavior |
| Complete / delete | Same web lifecycle handlers, including the restriction against completing an entire recurring series |
| Copy | The web's selected-day rolling week choices, up to seven target dates; existing copy handler preserves duration and skips duplicate title/start records |
| Patient → appointment | Reuses the same full editor through `NativePatientAppointment` instead of maintaining a reduced separate form |

The new range endpoint returns only the current user's records/patients, distinct occurrence keys, calendar counts and a selected-day page. Stable `(start, event id)` ordering is paired with a 15-minute, authenticated-session HMAC cursor; legacy offset pagination remains a compatibility fallback. The cursor watermark rejects owner schedule mutations between pages, but it is not a long-lived MVCC snapshot across transactions.

The shared editor validates real dates, end ordering, recurrence end and patient identifiers. Ref locks prevent repeated taps. A network/receipt failure after submission freezes resubmission and directs the user to inspect the calendar. Loading errors cannot save a blank replacement event, and cancelling an initial read invalidates late responses. Account/range changes hide previous data before effects complete. Native navigation removal and Android back are guarded while a write is pending.

## Conflict advice

The inspected web validator has no atomic overlap exclusion rule. A new owner-scoped preflight computes active overlaps using the same occurrence engine, supports weekly records and excludes the event currently being edited. The native form requires explicit confirmation before saving when overlaps are found. It does not mutate records during the check.

This is advisory: the check and write are separate requests, and the web creator does not enforce a shared atomic exclusion constraint. Two clients can still race. No exclusive-slot guarantee or capacity certification is claimed.

## Verification

- TypeScript passed; **218 Node tests passed, 0 failed** (18 session, 46 realtime, 154 beta).
- Selected Python suite: **197 passed, 0 failed**, with 312 deprecation warnings; includes boot, account, patient, upload, chat/request, admin/security and selected social regressions.
- Five new backend cases verify reminder queue/off, weekly/month range and owner isolation, web edit/copy/complete/delete lifecycle, advisory overlap scope, and all 151 selected-day records despite more than 100 historical anchors.
- Seven mobile cases verify form date/patient/recurrence validation, duplicate-tap prevention, reminder-off payload, account-switch isolation, malformed calendar/receipt rejection, full patient-profile appointment entry, explicit overlap confirmation and real month-grid/editor interaction.
- The earlier appointment payload interaction test moved into the common-editor suite. Existing account-switch/pending-patient-mutation regression remains intact. Source-location checks were retargeted to the actual shared editor and date validators; expectations were not reduced to bypass behavior.
- Android/iOS Expo-Hermes JavaScript exports succeeded. No new package/native dependency, native signing/build, emulator or physical-device test performed for this change.

## Remaining acceptance

No authenticated production/device, actual reminder delivery, PostgreSQL concurrency/load, OS keyboard/back/background interruption, pixel-equality or store acceptance. Range expansion still uses the existing web query/occurrence engine; response pagination does not prove large-history query performance or 60,000-user capacity. Native create requests use the durable owner/request and payload fingerprints stored on ScheduleEvent: same-payload replay returns the original event, changed-payload reuse returns 409, and a previously deleted receipt returns 410. Cursor pages are short-lived and session-bound; legacy offset pages remain non-snapshot compatibility reads.

Real Android/iOS testing and CI remain release gates. New backend endpoints are not deployed; the installed APK is unchanged. The original P0–P3 scope remains in `mobile-web-parity-tracker-20261114.md`; no whole-module completion is asserted before those acceptance criteria are met.



## 2026-11-19 — Authenticated calendar cursor integrity

A source review of app/mobile_program_api.py found that the prior base64 JSON cursor contained an account tag but no MAC. Queries remained owner-scoped, so this was not a cross-account read path; however, a client could rewrite its own snapshot, after or final event ID and cause skipped/duplicated pages.

The cursor is now version 2 and carries a 32-byte HMAC-SHA256 over the canonical JSON payload. The MAC key is domain-separated from the authenticated opaque bearer session token. The range endpoint obtains that same token through _mobile_access_token; it is not copied into the cursor or persisted. A cursor is rejected with 422 after payload tampering, session-token rotation, account/date/view mismatch or invalid structure. The existing 15-minute expiry remains 410, and owner schedule changes during pagination remain 409. The response continues to set private, no-store and Vary: Authorization.

Added backend regressions for token-key derivation, session binding, signature tampering, future/expired snapshots, and the authenticated range endpoint's cache headers and tamper rejection. These tests are committed but were not run in the connector-only session. No schema migration, dependency, patient-data or reminder behavior changed.
