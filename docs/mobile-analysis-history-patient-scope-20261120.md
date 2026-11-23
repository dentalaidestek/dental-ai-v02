# Mobile patient analysis history scope — 20 November 2026

## Web-first behavior checked

The web patient profile builds its analysis history with an explicit
`Analysis.patient_id == patient_id` filter after checking the signed-in user's
access to that patient. The native profile history calls
`getAnalysisHistory(token, cursor, patientId, toothNumber)`; the client sends
`patient_id` and optional FDI `tooth_number` query parameters and rejects any
row whose `patient_id` or `tooth_number` does not match the requested scope.

## Defect found

The shared mobile `GET /api/mobile/v1/analyses` route accepted neither
`patient_id` nor `tooth_number`. It therefore returned every analysis owned by
the signed-in clinician even when the native screen requested one patient.
The response count was also owner-wide. The native client correctly rejected
the mixed-patient response, so a clinician with more than one patient having
analyses could see an error instead of that patient's history. The server also
transferred unrelated patient names and clinical-note metadata to the device.

## Change

- Accept optional `patient_id` and `tooth_number` filters.
- Resolve a requested patient through the existing owner/admin guard before
  querying; another account's patient returns the same 404 as a missing patient.
- Reuse the canonical FDI validator and reject malformed tooth filters with 422.
- Apply the same patient/tooth filters to the row query and total count.
- Keep the existing descending analysis-ID cursor and 50-row maximum inside
  the requested patient scope.
- Preserve the owner-wide history contract for callers that omit `patient_id`.

No new table, migration, provider call, clinical write path, polling, or
production data change was introduced.

## Regression coverage

- Python API regression: patient filter, tooth filter, matching count, cursor
  continuation, cross-owner 404, invalid patient/FDI rejection, and legacy
  owner-wide list behavior.
- Node client regression: query construction, bearer token, cursor, and
  fail-closed rejection if a response contains another patient's analysis.
- Registered in `mobile/package.json` `test:beta` and the manual
  `native-clinical-security` workflow job.

## Validation boundary

The committed Python/Node tests could not be run against a repository checkout
in this execution environment. GitHub Actions remains manual-only. At the
starting branch head `a80fb7263643dd2d0a45d437d71a8b90b1c9bcca`, the combined
commit status and PR-triggered workflow-run list were empty. The last available
Android typecheck and Security Recovery jobs had zero steps and their log
downloads returned 404; neither TypeScript nor pytest started. No green CI,
full Android typecheck, physical-device test, or 60,000-user capacity claim is
made.

No merge to `main`, live deploy, migration, APK/IPA publication, or patient
record mutation was performed.
