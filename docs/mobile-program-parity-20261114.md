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

The new range endpoint returns only the current user's records/patients, distinct occurrence keys, calendar counts and a selected-day page. Stable `(start, event id)` ordering prevents nondeterministic ties within offset pages. It does not create a database snapshot across concurrent requests.

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

No authenticated production/device, actual reminder delivery, PostgreSQL concurrency/load, OS keyboard/back/background interruption, pixel-equality or store acceptance. Range expansion still uses the existing web query/occurrence engine; response pagination does not prove large-history query performance or 60,000-user capacity. Offset pages and mutation receipts are not durable snapshot/idempotency contracts.

Real Android/iOS testing and CI remain release gates. New backend endpoints are not deployed; the installed APK is unchanged. The original P0–P3 scope remains in `mobile-web-parity-tracker-20261114.md`; no whole-module completion is asserted before those acceptance criteria are met.
