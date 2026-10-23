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
