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

Outstanding: real Gemini audio/clinical scenarios (no local API key), real-device/browser microphone and lifecycle QA, real Gemini Live transport/audio validation and clinical alert latency, broad professionally reviewed source coverage, structured longitudinal medical profile, clinical correctness and privacy evaluation on synthetic realistic conversations. Existing clips are not continuous realtime listening; these checks occur after processed segments.

No main merge or production deployment.


## Continuous Live implementation
The dashboard now has a feature-gated Voice Examination card leading to /voice-exams, an owner-scoped bounded patient search or new anonymous patient creation. Names can later be applied through the existing review.

The /patients/{id}/voice-exam/live WebSocket checks feature state, exact Origin, authenticated active clinician ownership and explicit consent before any provider connection. Gemini credentials stay in a server header. The model defaults to gemini-3.5-transcribe-live; VOICE_EXAM_LIVE_MODEL can override it. VOICE_EXAM_LIVE_ENABLED=0 disables Live separately; all voice functions remain disabled by the overall VOICE_EXAM_ENABLED default.

AudioWorklet converts mono microphone input to PCM16 at 16 kHz in bounded 100 ms packets, including a final partial flush. Interim hypotheses are display-only; finalized transcription batches feed the existing bounded clinical-context extraction/review pipeline. This is continuous microphone streaming, not the 90-second manual recorder; manual clips remain an alternative. Clinical warnings depend on downstream finalized-text extraction and source assessment, not a guaranteed instantaneous medical alarm.

Pause/finish signal audioStreamEnd and wait briefly for a finalized response. Unconfirmed tails are indicated. Backpressure/disconnection stops the microphone and requires explicit restart; finalized clinical context survives in the current page, but missing audio is never replayed or guessed. Backgrounding pauses the microphone. Navigation/discard/save clear transient text and stop resources. No background audio archive or automatic paid reconnect.

Limits: four active proxy streams per process, one per owner per process, 30 minutes per session, bounded PCM frames/rate/provider messages and extraction queue. These are process-local, not a distributed concurrency guarantee. A new stream can resume with clinical context after explicit restart.

Validation: 51 Python tests pass (including WebSocket auth/origin/consent, mocked provider end-to-end transport, flush and malformed frames), plus three Node harnesses for review lifecycle, Live lifecycle and 16/44.1/48 kHz PCM resampling/tail flush. They do not establish real Google authentication, microphone/browser compatibility, transcription quality or clinical accuracy. A real Gemini key is not available in this workspace. Real service/device and retention checks remain required before enabling patient use. No main merge or production deployment.
