# Program inline-add parity — 2026-11-20

## Web-first behavior inspected

Before changing native code, re-read:

- `app/templates/program.html`: every rendered Today/Week date group has an inline add link after its event list. Today links to `/program/new?day=<group-date>`; Week links to `/program/new?day=<group-date>&type=CLASS`. The empty-state action also carries the selected focus date. Month uses its calendar/header navigation rather than per-day inline add.
- `app/templates/program_form.html`: the canonical form consumes the selected `day` and `type`, uses local datetime fields, and retains the shared title, patient, reminder, location, recurrence and notes controls.
- Native comparison: `NativeProgram.tsx` had a global add button and an empty-list action, but no add action after populated day groups. Its editor used only `page.suggested_start_local`, so a user could not start a new entry directly on a non-focused day in the visible week.

## Changes

- Added `programInlineAdd.ts` to map Today to APPOINTMENT and Week to CLASS while carrying the exact selected date. Month returns no inline action.
- Added `programDateTimeOnDay` so the editor applies the selected date while preserving the server-suggested wall-clock times and any overnight end-day offset. Invalid source/target dates fail closed.
- Added one inline add action after each fully known day-group boundary in the native list. If the final loaded cursor page may continue the same day, the last action is withheld until that page is loaded; this avoids placing an add action in the middle of a date group.
- Passed `initialDate` into `NativeProgramEditor`; the empty-state action also carries the focused date. Existing patient ownership, conflict advice, request-key recovery and save semantics are unchanged.
- Added pure helper tests and component regressions for Today/Week type/date, editor date/time, per-group placement and cursor-boundary behavior.

## Validation

Executed in an isolated Node/TypeScript harness:

- `node --test programInlineAdd.cjs`: **3 passed, 0 failed**.
- `tsc --noEmit --strict --target ES2020 programInlineAdd.ts`: **passed**.

The new React component regressions are committed in `mobile/tests/programParity.cjs` and registered through the existing `test:beta` script, but could not be executed in this connector-only runtime because the React and react-test-renderer dependencies are not installed here. The full mobile `npm test`, project-wide TypeScript check, Android Gradle/APK/device tests, backend security pytest and 60,000-user load tests were not run.

The branch head has no associated workflow runs or combined status entries. Android/Security workflows remain manual-only; no dispatch was made. No dependency, database migration, provider, patient-data write, main merge or production deploy was performed.
