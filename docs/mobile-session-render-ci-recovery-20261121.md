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
