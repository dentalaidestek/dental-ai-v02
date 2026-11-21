# Mobile session-render CI recovery — 2026-11-21

## Web-first review

Before changing the native/test code, re-read the canonical web flows:
- `app/templates/patient_detail.html`: patient hero, quick actions, editable patient information, clinical-media gallery, analysis and treatment history.
- `app/templates/program.html` and `app/templates/program_form.html`: today/week/month navigation, date grouping, inline add, event actions, patient selection, reminder and recurrence fields.
- `app/templates/notes.html` and `app/templates/notes_ai.html`: course creation/search, material readiness, source-backed study, quiz and answer actions.

The corresponding native paths are `App.tsx` / `NativePatientProfile`, `NativeProgram` / `NativeProgramEditor`, and `NativeAcademic`.

## Latest-head CI findings before the fix

At branch head `56175560050408c70173577924e45594b989633b`:
- Android run #4604 was pending with no job records when inspected; no fresh typecheck result was available yet.
- Security Recovery #2303 had native voice, clinical and support passing. Python/PostgreSQL security was still running.
- Native Social failed because `socialScreens.cjs` still asserted the retired token-derived patient key, while `App.tsx` correctly used `useSessionRenderKey`.
- Native Program failed because its VM renderer did not map the new default-export hook; React received a non-callable module object.
- Native Academic exposed a real source defect: `NativeAcademic.tsx` called `useSessionRenderKey` without importing it. Its VM renderer also lacked the hook mapping.

These were source/test-contract issues, not a server authorization bypass. The CI logs, rather than the workflow's aggregate red state, were used to separate them.

## Changes in this recovery

1. Added a test-only loader that compiles and exposes the production `useSessionRenderKey` hook with the real React instance and existing opaque-key helper.
2. Imported the hook in `NativeAcademic.tsx`.
3. Mapped the production hook into the Program and Academic VM component harnesses.
4. Updated the patient navigation assertion to require the opaque `profileRenderKey` boundary and the account/patient scope.
5. Added a React renderer regression proving stable identity within a session, rotation on account/token scope change, and no credential material in the key.

## Validation boundary

The changes are committed on `feature/mobile-web-parity-20261110`. Fresh Android and Security Recovery results must be read from the final commit before calling the recovery green. A passing VM regression does not replace a physical Android/iOS account-switch test.

No patient record, audio, clinical image, API authorization, provider prompt, database schema or migration was changed. No main merge, production deployment or store release was performed.


## Second-wave beta evidence and fixes

Android run #4606 (run `44925075384`, tested head `f88d4abe97737f784b74543e73d666392a5d2db3)):
- TypeScript typecheck, session/auth tests and realtime/pagination tests passed.
- The internal APK job completed successfully.
- The beta suite reported 920 passing and 54 failing tests. The failures were cascading VM-renderer setup errors, not 54 independent clinical defects:
  - The new hook bridge declared a top-level `const exports`, colliding with Node's CommonJS wrapper parameter and preventing the helper module from loading.
  - Program and Academic harnesses had been mapped to that broken helper.
  - Relationships, Professional/Account (two VM loaders) and Expert Performance still lacked the hook mapping, producing `useSessionRenderKey_1.default is not a function`.
  - The patient navigation test had already been updated to the opaque key contract.

Follow-up commits on the same feature branch:
- Renamed the bridge's local object to `hookExports` so it no longer redeclares CommonJS's `exports` binding.
- Added the real production hook mapping to Relationships, both Professional/Account renderers and Expert Performance; retained Program and Academic mappings.
- Expanded the shared contract test to cover all of those renderers and extended the React hook test to rotate on token, patient and account changes.
- A local isolated Node smoke check of the bridge passed: callable default export plus five scope transitions, with no credential text in any key.

The smoke check is intentionally not represented as a full beta-suite pass. The code-fix head was `f3a310ce748b70442a4521d4d8bb41341c151060`; this documentation follow-up makes the final branch head `f52b9e8ee1f5306e6da7b863591cf377fcecbf99`. No new Actions run is associated with this head; Security Recovery run #2305 remains pending without job records. The fixed harnesses therefore still need a fresh current-head CI execution before the recovery can be marked green.


## 60k-scale follow-up gap

The same branch review found that `WorkJob.enqueue()` uses one PostgreSQL transaction-scoped advisory lock for every admission, then counts all queued/running jobs before enforcing the global 1,000-job cap (and per-owner 32-job cap). This preserves an exact global bound but serializes admission during bursts. Render also sets `DENTAL_PROVIDER_MAX_INFLIGHT=4`. The technical audit's 34-peak-analysis concurrency is a planning estimate, not a measured load result. These limits and the lock were deliberately left unchanged; next validation is an instrumented burst test measuring admission wait, queue depth/age, provider occupancy and completion throughput before selecting a safe sharded/atomic admission design.
