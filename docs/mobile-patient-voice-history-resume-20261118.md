# Patient profile — approved anamnesis foreground recovery (2026-11-18)

## Web-first comparison

Before changing native code, reviewed the current branch's `app/templates/patient_detail.html` and the patient-profile rendering around the conditional `voice_history.fields` block.

The web patient detail renders only hekim-onaylı fields (medical history, medications, allergies, family history, dental history, oral habits and materials), with the source voice-exam analysis ID and the notice that these are prior approved statements. The page receives a fresh server-rendered snapshot when opened.

The native `NativePatientVoiceHistory` already had navigation-focus and realtime refresh. Unlike the adjacent `NativePatientHistory`, it had no React Native `AppState` listener. The parent `NativePatientProfile` refreshes the general patient payload on foreground, but that does not refresh the separately fetched `/patients/{id}/voice-exam/history` snapshot. If a voice review was approved while the app was backgrounded and its realtime event was missed, the anamnesis card could remain stale until navigation or manual refresh.

## Change

- Added `patientVoiceHistoryRefresh.ts`, a pure policy that refreshes only for a focused screen transitioning from `background` or `inactive` to `active`.
- Wired the policy to the existing `NativePatientVoiceHistory` request and removed the listener on effect cleanup.
- Repeated `active` notifications do not create extra reads; there is no timer, polling loop, new endpoint or dependency.
- Existing navigation-focus refresh and realtime event handling remain.
- Existing request-generation/account/patient scope guard still rejects a late response from the previous patient.
- The existing voice API GET continues to use its no-store request behavior; no clinical text or patient identity is added to logs.

## Regression coverage

Extended `mobile/tests/patientVoiceHistory.cjs` with five cases:
1. Only focused background/inactive-to-active transitions refresh.
2. Foreground return refreshes approved anamnesis once even if `active` repeats.
3. A blurred patient screen does not fetch on resume; navigation focus still refreshes.
4. A late resume response from patient A cannot replace patient B's anamnesis.
5. The AppState listener is removed on unmount.

The existing test file is already included in `npm run test:beta`. Added it to the Security Recovery `native-clinical-security` Node regression command as well.

## Validation performed in this run

- Isolated Node helper policy test: **1/1 passed**.
- Strict TypeScript compile of the standalone helper with global TypeScript 5.8.3: **passed**.
- The five committed React renderer tests were added but were **not executed** here; this connector runtime does not contain the repository's installed mobile dependencies.
- Full `npm run typecheck`, `npm run test:beta`, Security Recovery, pytest, Expo export, Gradle, and physical Android/iOS acceptance remain unverified.

## CI and safety

Starting branch HEAD was `aa33349dc9159d2fe2d08967f00f393af73d21e6`. Its associated PR-triggered workflow list and combined status were empty.

The latest inspected old push-triggered Android test-APK run was [#44273348890](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44273348890). Its `apk` job `134695200557` had `steps: null`; the step query returned an empty list and the job-log download returned `BlobNotFound 404`. The workflow source on the current branch is now `workflow_dispatch` only, as are Mobile Android CI and Security Recovery. This is a pre-step Actions runner/job-log allocation failure; it did not run npm, TypeScript, Gradle or pytest. The exact hosted-runner/account/billing cause is not exposed by the available GitHub records. No source-level typecheck failure can be diagnosed from that run.

No main merge, production deployment, migration, APK/IPA publication, clinical record mutation or live patient-data access was performed.
