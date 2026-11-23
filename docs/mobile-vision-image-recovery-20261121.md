# Native vision viewer recovery and CI repair — 2026-11-21

## Web-first review

Reviewed before editing:
- `app/templates/analysis_viewer.html`
- `vision_service/templates/radiograph_viewer.js`
- `vision_service/templates/intraoral_viewer.js`
- `mobile/src/NativeClinicalReview.tsx`
- `mobile/src/NativeVisionViewer.tsx`
- `mobile/src/visionModel.ts`

The web viewer fetches the selected image as an authenticated same-origin resource, validates the response as an image, creates a temporary object URL, revokes the previous object URL on asset change, and keeps inference snapshot retrieval separate from image retrieval. Radiographic Grad-CAM attention is read from `gradcam_attention`; intraoral findings do not use that pool. Native modality selection and the attention/list-only geometry rules match those web paths.

## Starting-head CI evidence

Starting head: `4c782d11ab1cebc96c1e9b204261d29514addd03`.

- Android run [44854401839](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44854401839): TypeScript typecheck passed; session/auth and realtime/pagination passed; Android/iOS Expo export passed; internal Android APK build passed. The beta suite reported 891 passed / 23 failed out of 914.
- All 23 failures came from `mobile/tests/toothChartLifecycle.cjs` failing during component loading with `unexpected import ./toothChartSurfaceSelection`. The native component had gained this helper import, but the VM test harness's explicit module map had not. The assertions did not run; this was a test-harness wiring defect, not 23 independent clinical failures.
- Security Recovery [44854401875](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44854401875): Python security/PostgreSQL and all native clinical, academic, voice, social and program jobs passed.

## Changes

1. Added the missing `toothChartSurfaceSelection` mapping to the tooth-chart lifecycle VM harness. No application guard or clinical write behavior was weakened.
2. Added an explicit retry action when the native viewer image itself fails to load. Retry increments only the private Image component key; it does not call `getVision`, create a WorkJob, or spend another inference request.
3. Asset/account/analysis changes reset the image error/retry state. A successful image load clears the error.
4. Added renderer regressions for image-only retry without inference repetition and for switching to another authorized asset after an image failure.

## Verification boundary

Five commits were pushed to the development branch. The new HEAD's Android and Security Recovery workflows must execute before these fixes can be called CI-green. The tests are registered in the existing `npm run test:beta` suite. No local full Expo checkout was available in this run, so no local full-suite pass is claimed.

Real Android/iOS image orientation, device cache behavior, network interruption, accessibility and screenshot parity remain device-acceptance items. 60,000-user load capacity remains unverified.

No main merge, live deploy, production migration, APK/IPA publication or patient-record mutation.
