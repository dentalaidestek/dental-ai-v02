# Native Program swipe navigation parity — 2026-11-19

## Web flow inspected first

Inspected `app/templates/program.html` before changing the native screen. The web page:
- records horizontal touch movement on the Program surface;
- ignores movements shorter than 65 CSS pixels;
- requires horizontal movement to be at least 1.5 times the vertical movement;
- navigates to the server-provided previous/next period URL;
- clears transient touch state on cancellation and falls back to full navigation if fragment navigation fails.

The native `NativeProgram` screen already had Today/Week/Month tabs and previous/next arrow controls, but did not implement the web page's horizontal period gesture.

## Native change

Added `programSwipeDirection()` as a pure, shared rule matching the web threshold and direction. The native Program root now uses React Native's responder system to:
- swipe left to the API-provided next period;
- swipe right to the API-provided previous period;
- ignore short, vertical and invalid gestures;
- refuse gesture navigation while an unresolved action intent, mutation or copy dialog is active.

The gesture changes only the calendar's selected period. It does not create a second data source, add polling, change reminder behavior, or alter event ownership and mutation receipts.

## Regression coverage

Added `mobile/tests/programSwipe.cjs` for direction, exact threshold, diagonal rejection and invalid numeric input. Registered it in `npm run test:beta`.

## Validation limits

The helper and regression test were materialized in an isolated Node harness from the committed source:
- `node --test mobile/tests/programSwipe.cjs`: 2 passed, 0 failed.
- `tsc --noEmit --strict --target ES2020 mobile/src/programSwipe.ts`: passed.
- `mobile/package.json` parsed successfully and the new test is present in `test:beta`.

This validates the pure gesture rule only. The complete mobile `npm test` / project `tsc --noEmit`, Android Gradle/APK/device validation and backend security pytest were not executed. The latest branch head has no commit statuses or associated workflow runs; previous hosted jobs failed before usable steps/logs and their log downloads returned `BlobNotFound 404`. Do not treat the isolated helper check as a passing Android typecheck or CI run.

No main merge, production deploy, patient-data mutation or workflow dispatch was performed.
