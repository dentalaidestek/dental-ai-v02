# Native analysis session-key privacy — 2026-11-21

## Web-first review

Compared the authenticated web analysis composer and viewer flow in `analysis_new.html`, `patient_detail.html`, and `analysis_viewer.html` with the native `NativeAnalysisUpload → NativeDentalAI → NativeClinicalReview → NativeVisionViewer` path.

## Finding

Three native component identity boundaries interpolated the raw bearer token into React keys: the upload composer, clinical review, and image viewer. React keys are not request headers and do not need credentials. Including the token creates an avoidable path for credentials to appear in renderer/debug inspection surfaces and couples component identity to a secret string.

## Change

- Added `nextSessionRenderKey()`, which emits an opaque process-local monotonic identity without accepting or serializing a token.
- The analysis screen rotates its opaque identity when the authenticated token or account changes. Upload and clinical-review components retain their remount-on-session-change behavior without embedding the bearer token in keys.
- The clinical review independently rotates the viewer scope on token changes. Both the image component and the selected-asset viewer use this opaque scope, so a same-user token refresh still remounts the private image child.
- Authorization headers and private `cache: 'reload'` image loading remain unchanged.
- Added AST-backed regressions for JSX `key` expressions and helper tests for opaque uniqueness.
- Registered the regression in `npm run test:beta`.

## Safety and validation boundary

No API, backend authorization, storage, database, image bytes, prompt, provider or clinical record was changed. No raw token is persisted by the new helper. The test is committed and registered; it is not claimed as executed until the new-head Android CI completes. No main merge or production deploy was performed.
