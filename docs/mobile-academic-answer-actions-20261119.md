# Native Academic answer actions — 2026-11-19

Web-first comparison covered `app/templates/notes_ai.html`, its `addAnswerActions` handler and the owner/course/message-scoped `save_feedback` route in `app/academic_quiz_interactions.py`.

## Findings

- Web answer cards expose copy and persistent like/dislike actions.
- Native already had like/dislike, but each reaction called the full `refresh()` path. That reloaded workspace, timeline, quizzes, index readiness and learning progress even though only one message's vote changed.
- Native had no corresponding answer-level share action.

## Changes

- Added `academicAnswerActions.ts` for safe vote normalization/toggling and readable answer/quiz share text.
- Added `NativeAcademicAnswerActions.tsx` with accessible native share, like and dislike actions.
- The feedback API now validates the exact `{ok:true,vote}` acknowledgement before publishing local state.
- A successful reaction updates only the matching timeline message. It no longer performs the five-endpoint workspace refresh.
- Failed reactions roll back their optimistic state; no answer text or source data is sent to the feedback endpoint.
- Added nine helper/component/API regressions in `mobile/tests/academicAnswerActions.cjs` and registered the suite in `npm run test:beta`.

## Validation limits

GitHub source-contract review passed 10/10 checks after the final test-file update. The nine committed Node/React renderer tests, full `npm run typecheck`, `npm run test:beta`, Expo export and Android build were not executed in this connector-only run. The new test suite is committed and registered; it is not claimed as passing.

The native action intentionally uses the operating system share sheet rather than adding an unverified clipboard dependency. Exact one-tap clipboard parity with the web `Kopyala` action remains open.

No new dependency, database migration, patient-data mutation, main merge, production deployment or CI dispatch.
