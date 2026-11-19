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

The source and package-script changes are committed. The test was not executed in this environment because no working checkout/dependency installation or GitHub Actions runner is available. The latest branch head previously had no commit statuses or workflow runs; existing hosted jobs failed before steps and their logs returned `BlobNotFound 404`. Do not treat this as a passing Android typecheck or CI run.

No main merge, production deploy, patient-data mutation or workflow dispatch was performed.
