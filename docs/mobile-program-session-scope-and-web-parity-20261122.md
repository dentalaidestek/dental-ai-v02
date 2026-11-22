# Program native/web parity follow-up — 2026-11-22

## Baseline and CI

Starting branch HEAD: `c603d71482e698a92c5e9e94310f24f34da7fb45`.

- Android run `45005452033`: completed successfully. Typecheck and internal Android APK build passed.
- Security run `45005452043`: workflow conclusion was failure, despite all six native security jobs succeeding. The only failed job was the combined `security` job, specifically step `Validate web form and live voice browser regressions`.
- The failed browser step runs `tests/analysis_new_upload_form.cjs`. Its final markup-contract assertions used over-escaped regular expressions (`\\\\b` and `\\\\.` in regex literals), matching literal backslashes rather than a word boundary/property separator. Corrected the expressions to `/\\b/` and `/\\./` forms. This is a test-harness defect, not a product typecheck failure.

## Web-first flow inspected

Canonical web path:

1. `app/templates/program.html`: today/week/month navigation, week strip, month grid, event cards, edit/complete/copy/delete actions, and AJAX fragment navigation.
2. `app/templates/program_form.html`: event type, title, local start/end, optional patient, reminder, weekly recurrence, location and notes.
3. `app/main.py`: `program_new`, `program_edit`, `program_complete`, `program_delete`, `program_copy_to_days`, and shared reminder queue helpers.
4. `app/mobile_program_api.py`: owner-scoped native API delegates validation and lifecycle semantics to the web handlers.
5. `ProgramReminderJob`: durable occurrence-level reminder queue; due jobs are claimed in bounded batches using PostgreSQL `FOR UPDATE SKIP LOCKED`; pending-only partial index supports due work.

Native parity surfaces inspected: `NativeProgram`, `NativeProgramEditor`, `NativePatientAppointment`, `programApi`, `programIntent`, `programModel`, and the existing program/appointment regression suites.

## Changes in this follow-up

- Fixed the failing browser regression's escaped regex assertions.
- Replaced raw-token-derived Program calendar `scope` values with the existing opaque `useSessionRenderKey` identity before they enter React state and async response ownership refs.
- Applied the same opaque scope strategy to Program editor async ownership refs. Account, event, and patient context changes still rotate the key.
- Added regression coverage for key stability within one session, rotation after session change, and absence of credential text in renderer keys / Program state scope wiring.

## Existing contracts preserved

- Patient IDs remain account-owned and only attach to APPOINTMENT/CLINIC records.
- Create retries use the durable account-scoped request key/receipt.
- Complete/delete/copy actions use persisted action intent and server-side reconciliation.
- Copy is serialized on the source event and uses owner-scoped unique request hashes to avoid duplicate copies.
- Program pages are owner-scoped and use signed, session-bound cursors with a short TTL.
- Reminder creation, cancellation, retry/backoff, deduplication, and realtime publication remain shared with web.

## Scale and remaining acceptance gaps

The repository already has owner/date, owner/snapshot, and pending-reminder queue indexes plus a synthetic 60,000-owner query-plan fixture in `tests/test_postgres_optimization.py`. These are query-plan regression fixtures, not a measured 60,000-concurrent-user capacity result. No live database benchmark was run in this follow-up.

The stale-edit gap is now addressed across web and native Program paths. Each event exposes an opaque SHA-256 revision derived from the owner, event ID and microsecond `updated_at`; the revision contains no patient or appointment content. Web edit forms post the revision in a hidden field. The web handler locks the owned row with `FOR UPDATE`, compares the submitted revision before validation/writes, and returns HTTP 409 without mutation when it is missing or stale. The submitted web draft remains visible but its Save button is disabled until the user explicitly reloads the latest record. Edit, complete and delete serialize on the same row and advance the timestamp monotonically. The older `/api/mobile/v1/schedule/{id}/complete` and `/api/mobile/v1/schedule/{id}` mutation routes were also moved onto the same row lock/touch helper so legacy clients cannot bypass revision invalidation.

Native event reads and mutation receipts include the same revision. The native update API requires `expected_revision`; its handler delegates to the same row-locked web edit handler so web and native writes share one concurrency boundary. On 409 the native editor preserves its local draft, fetches and displays the current server snapshot, and requires an explicit “Yerel taslağı son sürüme uygula” action before retrying with the new revision. A second concurrent edit still returns 409 and repeats the comparison; no automatic last-write-wins retry is performed.

Regression coverage now includes web stale-form rejection and draft retention, native stale-revision rejection, missing revision rejection, revision rotation after edit/complete/delete (including legacy mobile schedule routes), native compare/rebase/retry behavior, and a real PostgreSQL two-writer test proving that two concurrent submissions with the same revision yield exactly one write and one 409. The CI failure discovered at the start of this follow-up was a stale source-count assertion in the tooth-chart parity test: the new conflict-snapshot read added a fifth patient-identity check. The assertion was updated to account for that real guard rather than removing the guard.

No production data, migration, merge, or deployment was performed. Physical device acceptance and PostgreSQL concurrency/load execution remain release gates.
