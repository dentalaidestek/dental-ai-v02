# Native patient-detail lazy data — 20 November 2026

## Web flow inspected first

Reviewed `app/templates/patient_detail.html`, `app/templates/tooth_chart.html`, the web patient-detail handler, and the native profile/tooth-chart screens before changing the API.

The web patient profile and tooth chart are separate destinations. The native profile also mounts `NativePatientMedia` and `NativePatientHistory`, each with its own bounded/paginated API. The native tooth chart needs the FDI tooth and surface observations.

## Gap

The mobile `GET /patients/{id}` response always queried every tooth status, every tooth-surface status, and the first 20 patient-media rows. The profile screen did not consume the chart arrays and already loaded media through the dedicated paginated media endpoint. Opening a profile therefore performed three avoidable database reads and transferred duplicate media metadata.

## Change

- `include_chart` is now opt-in on the owner-scoped, private/no-store patient-detail endpoint.
- Ordinary profile reads return empty `teeth` and `surfaces` collections without querying those tables.
- The six native tooth-chart read paths explicitly request `include_chart=true`, including initial load, refresh and post-mutation reconciliation.
- Patient detail no longer fetches the duplicate 20-row media preview. The existing cursor-paginated `/patients/{id}/media` endpoint remains the source for the native clinical archive.
- The response shape stays backward compatible (`teeth`, `surfaces`, `media` remain arrays); ownership checks, `private, no-store`, treatment snapshot/cursor behavior and clinical write paths are unchanged.

This reduces the work performed by ordinary native profile opens without weakening the dedicated chart or gallery workflows. It is a query/payload reduction, not a measured 60,000-user capacity claim.

## Regression coverage added

- Node API test: profile request omits the chart query and the chart request opts in.
- Native chart lifecycle test: all six chart reads explicitly request the chart payload.
- Python API test: profile omits chart/media data, explicit chart read returns FDI observations, paginated gallery still returns the saved media, and another account receives 404.

## Validation limits

Read-back source-contract checks: 8/8 passed. The Node and Python regression tests were added but not executed in this environment. The current PR head had no check runs/statuses when inspected; older Android/security jobs ended before their first step with empty step lists and unavailable job logs. These records do not establish a source-level test failure or a pass. Full Expo typecheck, Android build/device validation, Python security suite and real concurrency/load tests remain open.

No main merge, production deploy, migration, APK/IPA publication or patient-record mutation was performed.
