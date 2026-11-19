# Native tooth surface applicability — 2026-11-19

## Web and backend flow checked first

Inspected `app/templates/tooth_chart.html`, the inline `selectTooth` / `setSurface` flow, the tooth history endpoint in `app/main.py`, `app/tooth_surface_status.py`, and the native `NativeToothChart.tsx` / `api.ts` contracts.

The web form and API accept both `INCISAL` and `OCCLUSAL`. The native tooth illustration already translated the occlusal pin to `INCISAL` for FDI units 1–3, but the two native surface-choice lists still exposed both values for every tooth. That made the editor internally inconsistent: an anterior tooth could be assigned an occlusal surface, and a posterior tooth could be assigned an incisal surface, even though the pin mapping already encoded the intended distinction.

## Change

Added `mobile/src/toothSurfaceOptions.ts` with a strict FDI guard for permanent quadrants 1–4 (units 1–8) and primary quadrants 5–8 (units 1–5).

- Units 1–3 expose `INCISAL`; units 4–8 expose `OCCLUSAL`.
- Both groups retain MESIAL, DISTAL, BUCCAL and LINGUAL.
- Invalid or incomplete FDI values return no writable options.
- Native selection, independent surface editing and surface-pin labels now use the same selected-tooth option list.
- Labels match the web terminology: Bukkal / Vestibül and Lingual / Palatinal.

The existing server-side patient ownership, expected-revision compare-and-swap, idempotent treatment receipts and clinical write paths are unchanged. No database migration or patient data mutation was made.

## Regression coverage

Added `mobile/tests/toothSurfaceOptions.cjs` and registered it in `npm run test:beta`.

Coverage includes permanent anterior/posterior teeth, primary anterior/posterior teeth, invalid FDI values, and native component wiring for both pickers and pin labels.

## Verification and limits

- Isolated Node.js 22.16 helper tests: 4/4 passed.
- Standalone strict TypeScript compile of the helper: passed.
- The committed component-wiring test is included in the beta suite but has not been run against a local full checkout.
- Full mobile typecheck, complete beta suite, Python security suite, Expo Android/iOS export, Gradle APK and physical-device acceptance remain unverified.
- Current Android and Security Recovery workflows are manual-only. No workflow was dispatched in this run because previous failed attempts generated noisy CI notifications and the latest branch head had no associated workflow run or status check.

No main merge, production deploy, APK/IPA publication or clinical record mutation.
