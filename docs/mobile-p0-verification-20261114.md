# Mobile P0 investigation — 14 November 2026

Source inspected: `c8f2070390d460939ca70097b1c0ee368abbeb53`, branch
`feature/mobile-web-parity-20261110`, draft PR #257. The PR targets
`feature/mobile-beta-20261110`, not main. Comparison to main reported 532 commits
ahead and 6 behind; no merge/rebase was attempted.

## Confirmed defects addressed

1. `app/mobile_analysis_api.py` used `Query` in route defaults without importing
   it. Importing `app.main` raised `NameError` at line 230, preventing application
   startup and security-test collection on this revision. Import corrected. A
   subprocess regression now imports the actual application and checks that
   unauthenticated patient/analysis requests return JSON 401 responses. The
   security recovery workflow includes this test and watches the affected file.
2. Protected clients handled 401 inconsistently. Patient, social and modern
   clients did not initiate a canonical session check; analysis and voice clients
   ended sessions directly on a feature-specific 401. All now confirm via `/me`.
   Concurrent checks share one probe; unavailable/invalid responses preserve
   credentials; no clinical mutation is retried. Foreground resume checks the
   active token and removes the old account's AppState subscription on cleanup.
3. History/restart analysis recovery required a selected patient but never
   restored that patient. Recovery now uses the server-authorized, identity-checked
   analysis patient. A patient-profile AI action now passes its actual patient ID
   through navigation and verifies it through the patient endpoint. Explicit
   patient actions cannot reopen a different patient's saved job. Selection
   remains visible outside the first search page without changing pagination
   offsets. Selecting another patient clears the old job; deletion events clear
   the selected deleted patient. Delayed old-account results are discarded.

## Validation

- Mobile `npm ci --ignore-scripts` succeeded using the committed lockfile.
- `npm test`: TypeScript plus 174 tests, zero failures. Includes 12 new mobile
  regressions: four session-health, one foreground lifecycle, seven recovery and
  patient-selection tests. The missing behaviors were demonstrated failing
  before their fixes; existing test expectations were not relaxed.
- `npx expo export --platform android --platform ios`: both JavaScript/Hermes
  bundles exported successfully. This is not a native APK/IPA build or device test.
- Isolated Python 3.12 environment installed repository requirements plus pytest,
  httpx, NumPy 2.5.3 and OpenCV headless 5.0.0.93. The following selected tests
  passed: 171, zero failures (210 existing deprecation warnings):
  - `tests/test_mobile_boot.py`
  - `tests/test_admin_fixed_email_otp.py`
  - `tests/test_security_hardening.py`
  - `tests/test_security_recovery.py`
  - `tests/test_auth_ui_recovery.py`
  - `tests/expert_social/test_api.py`
  - `tests/expert_social/test_native_auth.py`
  - `tests/expert_social/test_identity.py`
  - `tests/expert_social/test_safety.py`
  - `tests/expert_social/test_schema.py`
  - `tests/expert_social/test_comment_threads_api.py`
- The security-only subset above passed 76 tests. It is part of the 171 total,
  not an additional 76 tests.

## CI and execution limits

The initial commit's Android and three security/social workflows reported failure.
The Android typecheck job returned an empty steps list; downloading its logs
returned `BlobNotFound` 404. Local TypeScript passed before and after changes.
Therefore no TypeScript compiler defect is asserted as the cause of remote CI.
The startup NameError was reproduced independently using the branch source.

The private repository could not be cloned through the shell's unauthenticated
Git transport. Files were retrieved at the exact commit using the connected
GitHub provider for isolated local validation. Initial collection attempts hit
missing local source/dependencies; after supplying these, the selected suite
passed. The wider expert-social selection initially could not collect
`test_post_edit.py`/`test_moderation_lifecycle.py` (missing test_postgres helper) and
`test_relationships.py` (Playwright absent). These browser/PostgreSQL scenarios,
the complete repository suite and the complete CI suites are not reported passed.

Public HTTPS GET `/api/mobile/v1/patients?limit=30` returned JSON 401 without
credentials, confirming reachability from this environment only. No live
authenticated requests, patient writes, AI-provider calls, load tests or device
tests were performed. No secrets or patient data were logged.

## Remaining release blockers

- The screenshots' authenticated Android loading issue has not been reproduced
  on the user's device. The source defects above do not establish one common
  cause for every spinner. Verify a fresh release APK against the real account
  and record safe HTTP status/timing/build identity without clinical payloads.
- Native registration is absent: Login still links to `/register`; the inspected
  mobile API has no registration endpoint. Native password recovery also remains.
- VoiceExamEntry explicitly says the native microphone is unconnected; app.json
  blocks RECORD_AUDIO. Native capture, durable drafts and controlled persistence
  remain unfinished.
- Program still uses a text datetime input; calendar/date-picker parity remains.
- Clinical profile/anamnesis, academic upload/job parity, push delivery, iOS native
  device validation, and full product acceptance remain open.
- No physical Android device or iOS runtime was available; no new APK/IPA was
  produced locally. No 60,000-user capacity claim is made.

No main merge, live backend deployment or store publication was performed.
