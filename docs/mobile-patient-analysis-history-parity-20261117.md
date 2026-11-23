# Native patient analysis history parity — 17 November 2026

## Web flow checked before the native change

Re-read `app/templates/patient_detail.html` and the canonical `app/mobile_analysis_api.py` analysis-detail and protected-asset routes.

The web patient profile renders two separate image groups in each analysis detail:
- **Yüklenen görüntüler**: `ImageAsset` rows whose `image_type` is not `RADIOGRAPH`.
- **Radyografiler**: `ImageAsset` rows whose `image_type` is `RADIOGRAPH`; if none exist, the template falls back to the legacy `Analysis.radiograph_path`.

The native history previously rendered all `ImageAsset` rows in one combined group and only knew the protected asset-ID route. It did not render the web template's legacy radiograph fallback. Older analyses with `radiograph_path` but no RADIOGRAPH `ImageAsset` therefore showed no radiograph in native history.

## Changes

- The native analysis-detail JSON now returns only a boolean `legacy_radiograph_available`; it never returns the storage path.
- Added `GET /api/mobile/v1/analyses/{analysis_id}/legacy-radiograph`. It reuses the canonical analysis ownership check, resolves the existing storage path server-side, and responds with `Cache-Control: private, no-store`.
- Added a pure native presentation helper that groups non-radiograph and radiograph assets exactly like the web template.
- Native patient history now renders the two web-equivalent headings, shows the legacy radiograph only when the capability flag is true and no RADIOGRAPH asset exists, and sends the bearer token only in the protected image request header.
- Restored the web profile's separate `Tedavi önerisi` heading and result action for the analysis detail. Native status mapping now uses the same successful status set as the web template; `AI_FINAL` is no longer silently promoted to “Başarılı” when the web labels it “Yarım kaldı”.

## Regression coverage

- `tests/test_security_hardening.py`: ownership check, storage-path non-disclosure and private/no-store response contract.
- `mobile/tests/patientAnalysisHistory.cjs`: asset grouping, legacy fallback selection, authenticated route URL, no duplicate fallback when a RADIOGRAPH asset exists, and web-equivalent status labels.
- Registered the native suite in `npm run test:beta`.

## Validation limits

The changes and tests are committed on `feature/mobile-web-parity-20261110`. The new pytest and Node tests have **not** been executed in this run. The latest code-bearing Android typecheck and Security Recovery jobs still fail before any runner step; their step arrays are empty and log downloads return `BlobNotFound 404`. No compiler or test result is inferred from those workflow failures.

No production data or storage files were read or changed. No schema migration, merge, deploy, APK/IPA publication or clinical-record mutation was performed.
