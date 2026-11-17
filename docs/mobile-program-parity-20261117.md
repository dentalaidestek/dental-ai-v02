# Mobile Program parity — 2026-11-17

## Web flow reviewed first

Reviewed the live web source in the feature branch before changing native code:

- `app/templates/program.html`: today/week/month navigation, selected day, occurrence cards, edit/complete/copy/delete actions.
- `app/templates/program_form.html`: event-specific title labels/placeholders, patient selector, reminder options, recurrence, location and notes limits.
- `app/main.py`: `program_page`, `_program_range`, `_user_schedule_occurrences`, `_validate_schedule_input`, reminder queue helpers and web mutation handlers.
- `app/mobile_program_api.py`: native JSON calendar, opaque snapshot cursor, event receipts, conflict check and mutation adapters.
- `mobile/src/NativeProgram.tsx`, `NativeProgramEditor.tsx`, `programApi.ts`, `programModel.ts`, `NativePatientAppointment.tsx`.

## Defects fixed

1. **Istanbul cursor timezone:** recurring occurrence timestamps are naive Istanbul wall times. Cursor encoding and comparison previously called `astimezone(UTC)` on naive values, which interprets them in the host timezone. Late-day entries could then be rejected as belonging to the next day, and results could vary by runner timezone. Added an explicit wall-time-to-UTC helper and used it for both cursor encoding and page comparison.
2. **Copy-to-source-day parity:** web hides the source occurrence's date in the copy sheet; native exposed it. Native now filters the source date out.
3. **Edit timeout recovery:** the editor's recovery action previously queried only create receipts. An update has no create receipt, so its verify button was disabled. The editor now fetches the owned event and compares the server fields with the submitted draft before claiming success. A mismatch leaves the draft visible and permits a deliberate retry.
4. **Uncertain calendar action safety:** a manual “I checked” button could clear an uncertain complete/delete/copy state without contacting the server. It now requires a successful server refresh. The uncertain lock remains after a failed refresh and blocks additional mutations.
5. **Web form parity:** native title labels/placeholders now match the web event-type map; location is capped at the web's 160 characters; reminder and recurrence values and notes/location limits are validated before submission. The reminder hint points users to the device notification setting.

## Regression coverage

- Added `tests/test_mobile_program_api.py` for 00:15 and 23:30 Istanbul cursor round trips, cross-account cursor rejection and host-timezone-independent conversion.
- Extended `mobile/tests/programParity.cjs` for source-day filtering, web title copy, location limits, create/edit recovery and server-confirmed calendar action recovery.
- Registered the Python test in both the Security Recovery path filter and its pytest command. The native test is already included in `npm run test:beta`.

### Local isolated checks performed

- Python cursor reproduction: **3 scenarios passed** (late/early Istanbul times and cross-account rejection).
- TypeScript `programModel.ts` transpile + Node test: **1 test passed** for title copy, reminder validation, location limit and recurrence normalization.
- TypeScript syntax transpilation of the changed editor/calendar helper and JSX fragments: **4 snippets passed**.

The full repository Node suite, pytest suite, Android typecheck, Expo export and APK build were not executed locally because this environment has no GitHub checkout/network access and the linked React Native packages are not installed.

## GitHub Actions on final head

Final head for this work: `88bd13e5f5c053635eeaca0cbc0e6f2f30198b3a`.

- Android run `44165505887`: typecheck job `134330695566`, APK job `134330696148`.
- Security Recovery run `44165505730`: native voice security job `134330724701`, Python security job `134330725128`.
- Admin security run `44165505655`.

The Android and Security Recovery failed-job reruns were accepted. Their latest job records still have empty step arrays; log downloads return `BlobNotFound 404`. Therefore npm/tsc, Gradle and pytest did not start. This is a pre-step GitHub Actions execution/log allocation failure, not evidence of a source test failure. The available records do not identify whether hosted-runner capacity, repository/account configuration or billing is responsible. No source-level CI fix can be justified until GitHub supplies a runner and logs.

## Scale and remaining acceptance

The current calendar query scopes by owner and bounded date range, uses 50-item pages and a 15-minute snapshot cursor. Reminder jobs are durable, deduplicated per occurrence, processed in batches of 100, with a 300-second recovery interval and 30-day retention.

A 60,000-user capacity claim is **not** made. `_user_schedule_occurrences` still expands all matching weekly series for the selected range in Python. Snapshot-change checks filter by owner but `created_at`/`updated_at` do not have dedicated indexes in the current model. The next scale check is a PostgreSQL EXPLAIN/load test with realistic recurring-event distributions; any composite-index migration must be reviewed separately and is not included here. End-to-end push delivery and physical Android/iOS acceptance remain open.

## Distribution safety

PR #257 remains open and Draft. No main merge, live deploy, production migration, APK/IPA publication or real patient-record mutation was performed.
