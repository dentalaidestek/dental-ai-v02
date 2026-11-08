# Claude final review — current contract (7 November 2026)

Gemini transcribes audio. Claude performs structured extraction. In the default claude_web source mode, a separate bounded Claude research session receives only validated public topic IDs and generic drug concepts; its public evidence cache is shared across requests in the process. Claude then makes one final clinical-review request. Optional manual in-session clinical review remains a separate explicit action. There is no silent provider fallback.

This postlaunch change adds the supported full transient conversation (max. 72,000 characters) to the final Claude request, alongside current clinical values, source passages and clinician edits. Previously only the extracted context reached final review, so omissions could not be checked. The browser sends conversation_text; the backend minimizes recognized direct identifiers and administrative spans, and uses a transient conversation quote anchor for omitted clinical details. The conversation is not copied into final summary fields, patient records, work jobs or search queries. Recognizable identifier redaction is not full semantic anonymization; explicit patient/process consent remains necessary. Audio necessarily reaches Gemini when that option is used.

Final output remains bounded by 8,192 tokens, a 90-second timeout, output size checks and exact source/patient grounding. Same-exam duplicate pending work is rejected using authenticated(user_id,patient_id)+content fingerprint, and the pending map retains no raw transcript/result cache. Source-only retry reuse includes the full conversation fingerprint. This deduplication is processlocal; no crossworker exactly-once billing claim is made. Provider reservations bound configured concurrency, but daily/monthly spending ceilings require configured provider budgets.

Raw audio and full transcript never automatically become a saved patient record. The clinician explicitly chooses fields, teeth and appointment, then presses Onayla ve kaydet. The database commit precedes optional realtime delivery. Local session drafts expire 30 minutes after their last change; explicit logout stops writers and clears voice/social drafts without clearing unrelated preferences.

Configuration: ANTHROPIC_API_KEY and optional VOICE_EXAM_CLAUDE_MODEL (default claude-haiku-5-5). No new SDK/dependency. Source budgets remain at most 2 searches/3 fetches per research session; they cannot validate every possible procedure/material. Clinical suitability/accuracy is not established by schema or code tests.

Current verification and remaining gaps are recorded in docs/postlaunch_social_voice_2026-11-07.md. Full voice tests use mocked provider responses. The initial local run lacked app/data/voice_drug_sources.jsonl in the reconstructed checkout. The file exists in main and was restored byte-for-byte (Git blob e665733239c20a5248feeafbe08b8dbd39a0263f); all9 drug-source tests then passed. This was a local test setup issue, not evidence of a production source outage. Historical clean-audio omissions and warfarin/morphine ASR substitution remain unclosed clinical validation issues. Do not treat this implementation as a clinical-safety certification.

The following section is the historical initial rollout record and does not describe today's provider roles or full-conversation transport.

---

# Claude final review

The end-of-examination review now uses one Anthropic Messages request instead of
the previous final Gemini request. Speech transcription/extraction and the optional
in-session clinical tool remain on Gemini. There is no hidden provider fallback
or retry, and no additional final model call.

Configuration: ANTHROPIC_API_KEY is required; VOICE_EXAM_CLAUDE_MODEL optionally
overrides claude-haiku-5-5. The existing shared provider reservation/budget is used
under anthropic. Timeout90seconds; response size and output tokens are bounded.
No new SDK or dependency is needed.

Only current clinical field values, teeth, appointment, the uncertainty note and
retrieved evidence reach Claude. Patient first/last-name fields, raw audio,
transcript and private communication coaching are excluded. Direct numeric/contact
identifiers are redacted; this is not a claim of complete anonymization of free text.
The consent text explicitly names Claude and the data sent for final review.

The request uses output_config.format JSON Schema, with field/source identifiers
restricted to the supplied identifiers. Existing exact patient/source quote checks,
source eligibility checks and no-automatic-write behavior remain. Invalid, refused
or truncated responses fail rather than becoming a clean clinical result.

Extraction instructions now explicitly preserve planned drug names, formulation,
not-started status and spoken laboratory results. This is an instruction improvement,
not a proven lossless clinical fact store. Source retrieval is unchanged: changing
provider does not establish adequate interaction coverage or repair missing sources.

Validation:113 focused Python tests passed against repository-pinned FastAPI,
SQLModel, SQLAlchemy, Pydantic and Starlette versions. The final browser lifecycle
Node harness passed. Tests cover one Claude request, reservation, schema conversion,
no Gemini fallback, refusal/truncation rejection, and existing source/patient anchors.
These provider responses are mocked. No local Anthropic API key is available.

The sourced warfarin/miconazole baseline remains FAILED until the exact same audio
is retested with the new deployment, without supplying the expected answer to the
model. Planned medication preservation and the relevant source excerpt must both
be checked. No live accuracy or clinical-safety claim is made by these unit tests.

API contract reference: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
