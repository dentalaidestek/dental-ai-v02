# Native patient-profile render-key privacy — 21 November 2026

## Web-first review

Before changing the native profile, re-read the web reference and its server flow:

- `app/templates/patient_detail.html`: hero, quick actions, collapsed patient-information form, two-step delete dialog, clinical media, analysis history, doctor-approved anamnesis and treatment history.
- `app/main.py`: owner-scoped patient detail, revision-fenced profile edit, owner-checked delete, cursor-paged media/history.
- Native comparison: `mobile/src/NativePatientProfile.tsx`, `NativePatientMedia.tsx`, `NativePatientHistory.tsx` and `NativePatientVoiceHistory.tsx`.

The native profile already keeps the web section order and uses separate paginated media, analysis and approved-anamnesis sections. Its profile edit uses the same revision boundary and preserves conflicting drafts; this change does not alter those workflows.

## Defect

The profile's in-memory request fence is `scope = userId + token + patientId`. That is useful for rejecting stale async responses after an account, token or patient switch. However, the same bearer-token-bearing string was also passed as the React `key` to the clinical-media, analysis-history and approved-voice-history children.

React keys do not need credentials. Reusing the raw token as renderer identity unnecessarily exposed a secret to React renderer/debug surfaces and coupled presentation identity to the credential value. This was a native-only privacy-minimization defect; no token was sent to another service by this code.

## Change

- Added a stable, process-local opaque render identity using the existing `nextSessionRenderKey()` helper.
- The key is allocated once for the current profile scope and rotates only when the account, session token or patient scope changes. Ordinary re-renders do not remount the child sections.
- Kept the existing token-bearing `scope` exclusively for internal request/state fencing; it is no longer used as a React key.
- Applied the opaque key consistently to the three independently stateful child sections: clinical media, analysis history and approved anamnesis.
- Added an AST regression requiring all three child keys to use `profileRenderKey`, rejecting token/scope/user-ID key expressions and checking that the identity rotates with the profile scope.
- Updated the React-renderer test harness to load the existing TypeScript helper through the shared CommonJS bridge. Existing account-switch/draft-isolation tests remain in the patient-profile suite.

No API, authorization, storage, database, clinical payload, image bytes, provider or patient record was changed.

## CI evidence and limits

The immediately preceding code head `601c278bc00287212fe42804a4853a7faaf6acc9` completed:
- Android CI run [44908398660](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44908398660): TypeScript typecheck, session/auth tests, realtime/pagination tests, mobile beta regressions, Android/iOS JS export and internal Android APK build all succeeded.
- Security Recovery run [44908398676](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44908398676): Python/PostgreSQL security plus native clinical, support, social, voice, academic and program regression jobs all succeeded.

Those runs are for the parent head, not this render-key change. The new source and regressions are committed, but they are not called green until a workflow executes against the new HEAD. No local checkout was available for independent execution in this run.

No main merge, production deployment, store publication, migration or patient-data operation was performed.
