# Voice examination review

Draft feature; disabled unless VOICE_EXAM_ENABLED=1. Requires GEMINI_API_KEY; optional VOICE_EXAM_GEMINI_MODEL, otherwise DENTAL_CLINICAL_AI_MODEL. No new database migration. Do not enable on real patients before provider retention/account configuration and audio/device validation.

## Implemented flow
Consented bounded audio clips (90 seconds / 8 MB) or text go to Gemini generateContent. Each following clip carries at most 6 KB of transient structured clinical context: extracted fields, teeth and appointment utterances. Full prior transcript and coaching cannot be context properties. This preserves clinical continuity through model instructions; it is not a proven medical understanding benchmark.

Natural complaints, negation, speaker uncertainty and corrections are requested in extraction. The model returns a cumulative review. Updated field values reset prior selection. Communication and categorized decision barriers (cost, fear, time, trust, understanding, unclear) require exact short transcript evidence, remain transient and never go through the save endpoint.

Calendar dates are resolved by application code, not model dates. Explicit numeric dates, today/tomorrow or an unambiguous upcoming weekday with one numeric time and a short explicit acceptance can prefill/select the appointment. Vague times, same-day weekday ambiguity, multiple times, cancellation and missing acceptance require completion. Calendar creation happens with the final clinician-reviewed save. Existing weekly occurrences are checked for overlap. Voice bookings serialize by owner; other calendar routes do not share this lock. No claim of a system-wide exclusion constraint.

Names and age can update existing patient fields after selection. Systemic history, medications and allergies are saved as clinician-selected patient-reported clinical notes, not new dedicated PatientProfile columns. Clinical checks currently use current voice-review fields, not a complete verified historical medication/problem list.

## Clinical sources
Academic AI/course retrieval is removed. Fixed professional-document URLs are fetched without patient search text in outbound URLs or headers. Redirects are refused. Bounded HTML paragraphs are cached globally for one hour; no patient data enters the source cache. Current coverage is four ADA documents: diabetes, antibiotic prophylaxis, anticoagulant/antiplatelet medications and osteoporosis medications/MRONJ.

Changed clinical context triggers a source review after a segment; unchanged context is not automatically retried. If a source matches and is retrievable, one additional Gemini call appraises it with clinical fields, excluding patient first/last names. Output needs an exact patient-value quotation and exact source-excerpt quotation; invented citations are discarded. Considerations, missing information and source-supported alternatives are conditional clinician decision support, not treatment orders. A syntactically grounded quotation is not proof of semantic applicability; clinician review remains necessary. Existing results are invalidated when the voice summary changes, and stale responses cannot overwrite a newer assessment. Missing or inaccessible sources never mean no risk.

Coverage is deliberately limited, not a comprehensive indication/contraindication or drug-interaction engine. Context selection and passage ranking can miss relevant evidence. Live document retrieval is implemented; Gemini clinical/audio accuracy has not been measured in this environment.

## Privacy
Audio is kept in memory and not persisted by this application. Transcripts, source quotations and coaching are not accepted as save properties. Only selected edited fields, selected tooth findings and optional appointment become existing records. The browser does not copy raw tooth quotations into saved notes. Generic job payloads remain empty.

Discard, successful save and pagehide clear draft DOM text, fields, audio references, handlers, coaching, context, source query/results and calendar inputs. Requests are aborted and stale responses rejected. Late microphone permission cannot restart a departed view. This is reference clearing, not guaranteed physical memory erasure or cancellation of provider processing.

Extraction instructions minimize output to clinical content and omit unrelated private narratives. This is not a proven semantic privacy filter; selected free-text fields still require human review. Raw audio reaches Gemini before text minimization. Provider retention, processing terms and operational logging must be verified independently; do not claim zero leakage or legal compliance.

## Validation and remaining work
38 Python API/unit/template tests pass; actual browser-controller code also passes a Node DOM harness covering cumulative context, explicit selection, minimal save, coaching replacement and cleanup. JS syntax and Python compilation pass. All four fixed ADA URLs were successfully fetched with excerpts from this environment.

Outstanding: real Gemini audio/clinical scenarios (no local API key), real-device/browser microphone and lifecycle QA, Gemini Live continuous streaming and immediate alerts, broad professionally reviewed source coverage, structured longitudinal medical profile, clinical correctness and privacy evaluation on synthetic realistic conversations. Existing clips are not continuous realtime listening; these checks occur after processed segments.

No main merge or production deployment.
