# Voice examination review

Feature flag: VOICE_EXAM_ENABLED=1 (disabled by default). Requires GEMINI_API_KEY; VOICE_EXAM_GEMINI_MODEL overrides DENTAL_CLINICAL_AI_MODEL. No new database migration.

Audio uses bounded, consented clips (90 seconds, 8 MB maximum) sent to Gemini generateContent. No automatic paid retry or provider fallback. Audio is held in browser/server memory, not persisted. Text fallback is available. This is not a realtime Gemini Live implementation and has not passed real-device/audio validation.

Only the owning active clinician can access a patient's review. Exact transcript quotations support extracted fields. The clinician explicitly selects and confirms fields before an atomic, idempotent update to existing clinical notes, tooth records or an optional appointment. Raw transcripts are not stored in generic jobs. Systemic history currently becomes a clinician-selected patient-reported clinical note, not a dedicated PatientProfile field.

Academic AI/course retrieval is removed. Sources currently match topics against official ADA and SDCEP document links checked on 2026-10-22. This is a curated directory, not live document-content retrieval or patient-specific contraindication/interaction verification. Empty matches are not safety clearance. Do not present it as a completed clinical alert engine.

Communication suggestions require an exact transcript quote and stay in the review UI, outside the patient chart. Partial-recording omissions must not be treated as proven clinician failures. Marketing scope and systemic-history persistence require clarification.

Validation: 20 unit/API/template tests pass and JavaScript syntax check passes. Browser, microphone, real Gemini audio, realtime streaming and clinical source-content validation remain outstanding. Draft PR only; no main merge or production deployment.
