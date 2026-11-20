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
- Added six pytest cases for exact collisions, same path/different method, partial multi-method collisions, multiple primary routers, methodless/idempotent behavior, and case-insensitive method matching.
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
