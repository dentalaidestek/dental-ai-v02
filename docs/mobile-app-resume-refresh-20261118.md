# Patient-screen app-resume refresh gating — 2026-11-18

## Web-first review

Before changing native behavior, reviewed the current branch's web references:

- `app/templates/patient_detail.html`: patient identity and complaint, quick actions, optimistic-free profile form, explicit delete confirmation, clinical gallery, analysis history, approved voice fields, and treatment history.
- `app/templates/tooth_chart.html`: permanent/primary dentition switch, FDI tooth selection, tooth/surface state, note, history tabs and revision-bearing form submission.
- `app/main.py`: patient ownership checks, tooth/surface compare-and-set revisions, explicit treatment workflow, and patient profile/media handlers.

The web pages obtain their server snapshot when the page is opened or a user explicitly navigates/refreshes. They do not have an application foreground event that can repeatedly re-run the same screen query.

## Native gap found

Five native screens loaded on navigation focus and also called their loader whenever an AppState event reported `active`, without checking the previous state:

- `NativePatientProfile` — patient detail and the first treatment page
- `NativePatientHistory` — analysis history
- `NativeToothChart` — tooth/surface/treatment snapshot
- `NativePatientMedia` — private clinical-media gallery
- `NativeProgram` — calendar page

A repeated `active` notification could therefore trigger another identical GET even though the app had not returned from background. The issue is avoidable database/network work, not a measured latency or capacity claim. `NativePatientVoiceHistory` already had the correct background/inactive transition behavior, but its helper was voice-specific.

## Changes

- Added `appResumeRefresh.ts` with a pure gate that permits refresh only for a focused screen transitioning from `background` or `inactive` to `active`.
- Reused the gate from the existing voice-history helper without changing its public function name.
- Applied the gate to patient profile, analysis history, tooth chart, clinical media and calendar. Their normal navigation-focus load remains unchanged; realtime-triggered refreshes remain unchanged.
- Each listener snapshots `AppState.currentState`, updates its previous state on every event, and detaches on effect cleanup.
- Added a regression test for valid/invalid transitions and source-contract checks for all five screens; registered it in `npm run test:beta`.

No new endpoint, polling loop, timer, database schema, migration, clinical mutation, cache policy or provider call was added.

## Validation

- Pure transition regression: 1/1 passed locally using Node's test runner.
- Strict standalone TypeScript compile of the new helper: passed.
- GitHub source verification: all five native screens import/use the shared gate and snapshot `AppState.currentState`; the new test is registered in `test:beta`.
- Full mobile `tsc`, beta suite, Expo export, Gradle/APK and physical-device checks were not run in this environment. The repository could not be cloned because GitHub DNS resolution failed and this runtime has no mobile dependency tree.
- The Android and Security Recovery workflows are intentionally `workflow_dispatch`-only. No dispatch was sent, preserving the earlier request to stop repeated mobile CI email. The current branch head had no associated workflow run/status. The latest inspected older Android run and the older typecheck/security jobs ended before any step (empty step arrays); their log downloads returned `BlobNotFound 404`. Those records do not contain a TypeScript or pytest diagnostic, so they cannot establish a source-code failure. The hosted runner/log allocation problem remains outside this patch and needs repository Actions access to diagnose.

No main merge, production deploy, APK/IPA publication or patient-record mutation.
