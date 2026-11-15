# Native clinical AI result/review — 2026-11-15

Continues PR #257 / issue #258 on the mobile development branch. No main merge, production deployment or store publication. Android/iOS exports and test suites are source verification; physical-device and production inference acceptance remain open.

## Reproduced root cause

`app/ai_engine.py` validates preliminary/final clinical findings as `list[str]`. The web `result.html` renders these strings. Native `displayFindings` required every item to have numeric confidence and discarded every valid clinical string. A failing regression reproduced that mismatch before the fix. The native helper now preserves nonempty clinical strings without inventing confidence; structured vision objects still require valid confidence >=50%.

The previous NativeDentalAI result UI also omitted most_likely, treatment_options, treatment_cautions, preferred_approach, differential, recommended_evaluation, uncertainty and questions-to-FINAL. The new NativeClinicalReview displays those web sections with native text/table layout. It includes real owned image preview/zoom, saved clinical notes, FDI permanent/primary selection, explicit clinical answers/consent, canonical FINAL job enqueue, status/failed retry/cancel and foreground polling. It does not automatically write diagnoses or treatment into the patient's chart.

## Server authority and duplicate prevention

The additive mobile_clinical_api adapter uses the existing source_identity, _enqueue_work and canonical web note/viewer/job handlers. No provider or prompt changes. Source identity includes current patient, tooth/history and analysis inputs. A stale clinical revision cannot enqueue new FINAL work. Every required answer must be provided; bounds/FDI/server ownership remain enforced. Canonical WorkJob dedup matches the same source and answers; a persisted receipt is returned even after FINAL replaces the preliminary result. An uncertain response retains exact account/analysis/revision/answers in encrypted local storage for explicit retry. Definite 409/422 rejection clears unusable local answers and requires fresh review. No automatic paid retries.

Reads use the web legacy result-reference fallback as well as current result_path. Missing saved result and corrupt result are different states; corrupt content returns an error. Job status includes VISION, PRELIMINARY and FINAL, so a failed vision stage is visible even though the old web _latest_work helper omits it. Raw provider errors, patient content and tokens are not logged or included in diagnostics.

## Concurrent branch changes preserved

Preserved gallery/CI/upload changes through `1dd1e144f278a0b8c51d18491f58a7fef29731e1`, including atomic upload DB transaction, picker MIME/filename validation and account-scoped media actions. The new combined local run exposed three pre-existing gallery test defects: source regexes no longer matched added picker-generation/preview guards, and Error belonged to a different VM realm. Source expectations were replaced with actual stale-permission and failed-page retry UI tests; the VM uses the host Error constructor. Expectations were not loosened: old permission completion must not launch a picker, full refresh must hide stale images and report error, and failed older-page reads must preserve verified rows/cursor for an explicit retry.

## Files

New: app/mobile_clinical_api.py; mobile/src/clinicalApi.ts and NativeClinicalReview.tsx; Python/Node clinical regression files. Existing mobile router, NativeDentalAI, findings helper/tests, gallery behavior tests, package script, security workflow and tracker updated.

## Still open

Full native web viewer overlay/geometry parity, image type/clinical input/multiple-image composer UI, durable upload-receipt reconciliation, image EXIF/retention audit, manual-note receipt across process death, vision/final production inference quality and elapsed timing, source races under PostgreSQL concurrency, foreground/background/reconnect/device acceptance, native OS layouts/keyboard, signed Android APK/iOS build and store gates. No 60,000-user capacity certification. Adapters require an explicitly approved backend deployment before production APK use. Remote CI cause is not established by local green checks.

Final selected local verification with the concurrent branch changes preserved: TypeScript clean; **296/296 Node tests** (18 session + 46 realtime + 232 beta), **226/226 selected Python tests**, zero failures; Python emits 416 deprecation warnings. Six server clinical tests and seven native clinical workflow tests plus the string-finding regression are included. Android and iOS Hermes export succeeded. This does not assert that the complete browser/PostgreSQL suite, remote CI or real devices passed.
