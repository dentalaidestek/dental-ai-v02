# Mobile CI beta regression recovery — 2026-11-21

## Baseline evidence

Branch: feature/mobile-web-parity-20261110
PR: https://github.com/dentalaidestek/dental-ai-v02/pull/257
Pre-fix workflow: https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44926017477
Security workflow: https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44926017465

The Android workflow completed dependency installation, TypeScript typecheck, session/auth tests, realtime/pagination tests, Android+iOS Expo bundle export, and the internal Android release APK build. The beta suite reported 985 tests: 980 passed and 5 failed. The separate security recovery workflow passed all seven jobs (Python/PostgreSQL plus native Program, Clinical, Voice, Support, Social and Academic).

## Five beta failures and root causes

1. dashboardPresentation.cjs: stale assertion expected a token-derived Program React key. The production Program route already uses useSessionRenderKey and an opaque programRenderKey. The test was asserting the superseded credential-bearing implementation.
2. Three nativeAuth.cjs account-render tests: the VM loader did not map ./useSessionRenderKey to the production hook bridge, so CommonJS returned an empty object and React received a non-callable default export.
3. sessionRenderKey.cjs: detected a real privacy regression in Dental Flow's composer. Its React key interpolated user.id and the bearer token instead of the existing opaque sessionKey.

## Changes in this recovery

- Dental Flow's composer now keys from sessionKey plus a stable composer suffix. The existing account/session epoch and stale-request guards remain authoritative.
- All three NativeAccount VM renderers now load the real production useSessionRenderKey helper.
- The dashboard test now asserts the opaque Program key and explicitly rejects the obsolete token-derived key.
- Session-key regression coverage now guards both the Dental Flow composer and NativeAccount VM hook mapping.

## Safety and acceptance boundary

No API authorization, patient data, clinical media, audio, database schema, migrations, provider prompts, or clinical decisions were changed. No production data was accessed or modified. No merge to main, live deployment, or store release was performed.

The above is a source-level remediation record. The updated full beta suite must pass on the new HEAD before this recovery is considered CI-verified. A successful Security Recovery run does not substitute for the Android beta suite.