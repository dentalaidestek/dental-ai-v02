# Native React renderer identity audit — 2026-11-21

## Scope

Reviewed the web patient profile and program creation flows before changing the native navigation and editor mounts. Then scanned all 45 changed native TSX entry/components in this PR for JSX `key` expressions containing `token`, `accessToken`, `sessionToken`, `authorization` or `bearer`.

## Finding

The app-level wrappers and several nested screens used the bearer token as part of React renderer identity. Affected paths included patient profile, account photo/profile sections, expert performance, relationship lists, Academic AI library/course, Program editor, patient appointment editor, and consultation chat subviews.

React keys are not request headers and this finding does not establish a server-side authorization bypass. They are renderer/debug identity, however, and should never encode credentials. Token-derived keys can unnecessarily propagate credential material into renderer diagnostics/profiling and make session identity opaque only in appearance.

## Change

- Added `resolveSessionRenderIdentity` and `useSessionRenderKey`. The account/session scope stays in a component ref; the React key is only a process-local `dai-session-*` value.
- Replaced app-level credential keys with opaque session-scoped keys, including route render callbacks through `SessionScope`.
- Replaced nested account, professional, expert-performance, relationship, Academic, Program, patient-appointment and consultation-chat keys.
- Preserved remount boundaries when token, user, patient, course, appointment editor, relationship kind or consultation changes.
- Added an AST-based regression test that scans the 45 native TSX files changed in this PR and fails if a JSX key expression contains credential identifiers. Added scope-rotation tests for the pure resolver.

## Validation

At the starting head `e8ae2e38`, Android CI run #4591 completed successfully (typecheck, session/auth, realtime/pagination, beta regressions, Android APK and JS bundle export). Security Recovery run #2290 completed successfully across six native security jobs plus Python/PostgreSQL security, migration and concurrency checks.

The new renderer-identity commits were pushed after those runs. Their own latest-head CI is not yet confirmed in this note; use the run attached to the new branch head before treating the change as validated.

## Safety boundary

No main merge, production deployment, database migration, patient-data mutation, clinical provider/prompt change, or app-store release was performed.
