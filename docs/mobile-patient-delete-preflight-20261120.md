# Mobile patient delete preflight and Python recovery — 2026-11-20

## Starting evidence

- Work branch: `feature/mobile-web-parity-20261110`
- PR: #257 (open, Draft); issue #258
- Starting code head: `86de5f98e5095f93ba53e17f9478e791c6e6dda3`
- Android run #4230 (`44733791697`): TypeScript typecheck, session/auth, realtime/pagination, 878 beta tests, Expo Android/iOS export and internal ARM64 APK all passed. APK artifact was not published.
- Security Recovery #1928 (`44733791493`): 5/5 native security jobs passed; Python security job failed with 531 passed and 4 failed (841 warnings).

## Python failure root causes and changes

1. `test_patient_history_filters_tooth_and_marks_only_confirmed_voice_reviews`: the request returned 200, but the top-level `main.app.routes` inspection exposed only the web `/analyses` route and not the nested/prefixed API route. Moving the snapshot after the request did not fix the assertion. The test now checks the canonical `mobile_analysis_api.router` declaration, absence of the duplicate v3 GET route, and the real prefixed HTTP JSON/cache/owner/tooth contract. The revised assertion still needs a new CI run.
2. `test_web_analysis_selection_and_submission_share_four_image_limit`: the assertion expected the substring `toplam en fazla 4`, while the canonical Turkish response correctly says `toplamı en fazla 4`. The assertion now checks the complete semantic phrase case-insensitively; server copy and limit behavior were not changed.
3. `test_native_patient_delete_ui_fails_closed_for_unresolved_local_mutations`: the native delete gate did not include an unsaved profile draft. A clinician could edit patient fields locally and then delete the patient without first resolving that draft. Added `profileEditReady` to the gate, tied it to dirty/conflicted/revision-conflicted profile state, and added a fresh server snapshot check when the profile editor is open. If the snapshot differs, deletion stops before creating a durable delete intent or sending the DELETE request. The local draft remains available for explicit reconciliation.
4. `test_web_patient_analysis_and_treatment_history_are_bounded_and_owner_scoped`: the test replaced the cookie with literal `token2`, which is not a valid session token, so the correct response was 401 rather than the expected owner-scope 403. It now uses the fixture's valid second-owner token; unauthenticated and authenticated non-owner cases remain distinct.

## Commits in this continuation

- `09027f5` — require resolved profile edit state before patient deletion
- `229a11a` — re-read the open profile before creating a delete intent
- `5c62001` — explain why deletion is blocked in the native UI
- `a2ce748` — add native delete-gate and latest-snapshot regressions
- `e68d702` — correct canonical-route, image-limit-copy and profile-delete parity checks
- `1f41134` — use a valid second-owner session token in the web history test
- `b13c648` — remove the unverified lifespan explanation from the route-test comment
- `bc357f4` — qualify the route-test diagnosis pending rerun
- `4312db7` — add the new profile-edit readiness field to the existing delete-gate matrix
- `bc47e66` — assert the canonical router and actual prefixed response contract instead of a flattened app route path

## Validation status

The latest completed evidence before the final route-test adjustment is Security Recovery #1938 (`44741936659`) and Android #4240 (`44741936688`), both on parent head `4312db7`:
- Native clinical security: **249/249 passed**; native voice, academic, social and Program jobs also passed.
- Android TypeScript typecheck passed; session/auth **20/20**, realtime/pagination **52/52**, mobile beta **881/881**, and Expo Android+iOS export passed.
- Python security: **534 passed, 1 failed, 841 warnings**. The remaining failure is the brittle flattened app route-table assertion described above.
- Internal Gradle APK assembly was still running when this note was written; no artifact publication is claimed.

The final route-test adjustment is committed as `bc47e66` but has not yet been executed in CI. No test is marked passed for that final adjustment based solely on source inspection.

Physical Android/iOS acceptance, production PostgreSQL/R2 checks and the 60,000-user load test remain open.

No main merge, live deploy, migration, APK/IPA publication or production clinical-data mutation was performed.
