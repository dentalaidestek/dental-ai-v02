# Native vision image session isolation — 2026-11-21

## Web-first review

Reviewed the web viewer before changing native code:
- `app/templates/analysis_viewer.html`
- `vision_service/templates/radiograph_viewer.js`
- `vision_service/templates/intraoral_viewer.js`

The web wrapper switches the authenticated image URL and modality for each selected asset while keeping the vision snapshot request separate. The native viewer already used the authenticated `clinicalImage()` source with `cache: 'reload'`, and its image retry correctly avoided another `getVision()` request.

## Starting-head CI evidence

Starting head: `d524d54ebefee75574ebab70e00f60fa7f0cf7a0`.

- Android run [44859166468](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44859166468): TypeScript typecheck passed; session/auth and realtime/pagination passed; Expo Android/iOS export passed; the independent APK job passed. The beta suite had 914 tests: 914 passed? No — 914 total, 2 failed and 912 passed? The runner summary reports 916 tests, 914 passed and 2 failed. The failures were the two newly added viewer retry/switch tests.
- The failing assertions read `ReactTestInstance.key`. The installed React 19 test renderer does not expose the special React `key` as a normal test-instance field, so both assertions observed `undefined`. The application key expression itself was present.
- Security Recovery [44859166504](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44859166504): Python security/PostgreSQL, Native Voice, Academic, Program and Social passed. Native Clinical ran the same viewer test file and failed on the same two assertions (256 passed, 2 failed); this was not a separate clinical authorization failure.

## Changes

1. Added `clinicalAnalysisImageKey()` to `mobile/src/clinicalMediaPresentation.ts`. It accepts only the generated opaque `clinical-vision-scope-N` identifier and positive analysis/asset IDs plus a nonnegative retry revision. It never receives or serializes the bearer token.
2. Updated `NativeVisionViewer` to allocate a new opaque image scope when the authenticated token changes. The Image React key and testID now include that scope, analysis, asset and retry revision. A same-numbered analysis/asset after an account switch therefore remounts the private image component without putting the bearer token in its key.
3. Kept the current Authorization header and `cache: 'reload'` image source. The retry remains image-only and does not repeat the paid vision request.
4. Updated the viewer tests to assert the public `testID` rather than the renderer's inaccessible React key. Added account-switch isolation and late-error-from-previous-asset regressions.
5. Added helper tests for session, asset and retry identity separation and rejection of a bearer-like scope.

## Verification boundary

The new commits are on `feature/mobile-web-parity-20261110`. The updated Android and Security Recovery workflows must execute on the latest head before this work can be called CI-green. No local full Expo/React Native test environment was available in this run, so no local full-suite pass is claimed.

Real Android device acceptance remains open for image caching, account switching, network interruption, image orientation, accessibility and screenshot parity. The 60,000-user capacity target remains unverified.

No main merge, live deploy, production migration, APK/IPA publication or patient-record mutation.
