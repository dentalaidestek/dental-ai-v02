# Mobile API route registry — method-aware deduplication (2026-11-21)

## Starting point and CI evidence

Starting PR head: \`95273117e2e1fa377cd18f0ab0bd526c0fa6905d\`.

Before changing code, the exact-head workflow lookup returned:

- Android CI run \`44825333893\` (#4359): pending.
- Security Recovery run \`44825333919\` (#2058): pending.
- Both job-list queries returned an empty array.
- The combined commit status returned no status entries.

The available records therefore do not show a TypeScript, Node, pytest, PostgreSQL, Gradle, or Expo failure. No source-level CI failure is claimed. The hosted jobs had not reached a step, so a code failure cannot be inferred from these runs.

## Web-first route flow inspected

Read the current branch's \`app/templates/patient_detail.html\` and traced the web gallery's cookie-authenticated original-file route in \`app/main.py\`:

- Web gallery uploads and previews are tied to the selected patient.
- The web original-file route is \`/patients/{patient_id}/media/{media_id}/file\`.
- The canonical mobile original-file route is defined by \`app/mobile_api.py\` and is Bearer-authenticated.
- \`app/mobile_modern_api_v3.py\` contains an adapter route with the same method/path. \`app/main.py\` must keep the earlier canonical router authoritative before including the modern adapter.

The deduplication must compare method **and** path. It must not collapse the distinct cookie/web and Bearer/mobile route contracts.

## Newly found route-registry edge case

The inline helper introduced in the preceding commit removed a candidate route whenever *any* method on that route collided with an earlier router. FastAPI permits an APIRoute to declare more than one HTTP method. For example, if the earlier router owns GET on a path and the candidate route declares GET + PATCH, removing the whole candidate route also discards the non-conflicting PATCH handler.

That is a registry correctness defect, not a currently observed production endpoint failure. Existing mobile routes are mostly single-method declarations; the regression protects future multi-method routes and prevents accidental API surface loss.

## Changes

- Added pure helper \`app/mobile_route_registry.py\`.
- Route ownership is now collected by path and normalized HTTP method.
- Only colliding methods are removed; remaining methods stay attached to the candidate APIRoute.
- Routes without an HTTP method set (for example WebSocket routes) remain untouched.
- \`app/main.py\` calls the pure helper before mounting the modern router, preserving canonical router order.
- Added seven pytest cases for exact collisions, same path/different method, partial multi-method collisions, multiple primary routers, methodless/idempotent behavior, case-insensitive method matching, and a real FastAPI APIRouter/OpenAPI integration check.
- Registered the focused pytest file in the existing Security Recovery Python command. No new workflow trigger or duplicate CI path was added.

## Validation

An isolated Python execution of the helper logic passed six focused cases. The changed helper and test source were read back from the branch, and the Security Recovery command contains the new test path.

This is **not** a repository pytest run. The actual Security Recovery pytest job, Android typecheck, full beta suite, Expo export, Gradle/APK build, PostgreSQL integration, physical-device tests, and 60,000-user load test remain unverified until GitHub allocates runners and executes their steps.

## Distribution and privacy boundary

- No route authorization was weakened.
- No patient record, clinical image, transcript, or production database was read or mutated.
- No schema migration was added or run.
- PR #257 remains open and Draft.
- No main merge, production deploy, APK/IPA publication, or store release.


## Follow-up after the first hosted execution — 2026-11-21

The next available hosted run provided source-level evidence that was not available at the starting head:

- Android run #4364: TypeScript typecheck, session/auth, and realtime/pagination steps passed. The beta suite failed on two stale source-contract assertions; the APK job had started but was not yet complete at the time of this check.
- Security Recovery run #2062 completed: native clinical, native Program, native voice, and native Academic jobs passed. Native Social had one stale source-contract assertion (79/80 passed). The Python security suite passed 568 tests, the PostgreSQL optimization/concurrency suite passed 29 tests, and web duplicate-submit guards passed. The Python run included the six initial route-registry unit cases.

Both beta failures were caused by tests that still asserted the old inline route-registry implementation:

1. mobile/tests/social.cjs expected the removed _mobile_mounted_routes marker.
2. mobile/tests/patientMediaRoute.cjs expected a direct mobile_modern_router.routes list-comprehension assignment.

The implementation had deliberately moved to the pure app.mobile_route_registry.remove_shadowed_routes helper. The tests were updated to verify the helper import, canonical-router-before-modern-router order, and the continued presence of both canonical and adapter route declarations. The assertions now use literal source contracts rather than brittle escaped regexes.

The updated Social and clinical-media test source was read back from the branch. Ten focused source-contract assertions passed against the current GitHub file contents; the route helper's six isolated behavior cases also passed. These checks do not replace the repository Node test run.

After the two stale assertions were fixed, a real FastAPI APIRouter/OpenAPI regression was added. Code head is f762ae0cba07b33d1e82463dc624113062961679; the current PR head is d8165332ce959d5217768f29bb1b64c03a4649f8 after a documentation-only update. Android CI #4369 and Security Recovery #2068 were pending with empty job lists, then were cancelled when the later PR commit superseded them. The corrected Social and clinical-media source assertions therefore still need a hosted rerun. The new real-APIRouter pytest case was validated in an isolated FastAPI/OpenAPI check but has not run in hosted pytest.

No main merge, production deployment, schema migration, patient-record mutation, or store publication occurred.


## Real FastAPI route check

A local isolated check using FastAPI APIRouter objects confirmed that a candidate GET+PATCH route is reduced to PATCH when an earlier router already owns GET, and that the combined OpenAPI path still exposes both GET and PATCH. The repository pytest case now performs this same APIRouter/OpenAPI check. It is committed but remains pending execution by the hosted Security Recovery job.

Latest branch head after adding the real FastAPI regression: f762ae0cba07b33d1e82463dc624113062961679. Android CI #4369 and Security Recovery #2068 are pending with no job records at the latest check. Combined commit status is empty; no exact-head CI pass is claimed.


## Final run snapshot — 2026-11-21

Security Recovery #2062 is the strongest completed backend evidence for this pass: Python security/identity 568 passed; PostgreSQL migration, query-plan and concurrency tests 29 passed; web form duplicate-submit checks passed. Native clinical, Program, voice and Academic jobs passed. The only failed native security job was Social, where an old source assertion expected the pre-refactor registry marker; the assertion was updated. Android run #4364 passed TypeScript, session/auth and realtime/pagination, but the beta suite failed only the two stale route-registry source assertions described above. Both were updated afterward. The Android APK build in #4364 had not finished at the last available step check.

The seven-case route-registry pytest file now also contains a real FastAPI APIRouter/OpenAPI test. Its behavior passed an isolated local FastAPI check, but this seventh case has not yet been executed by hosted pytest. The latest exact code-head workflows were superseded before any jobs began; current PR head has no combined status checks. Do not describe the corrected native beta suite or the new APIRouter case as CI-green until a fresh run completes.
