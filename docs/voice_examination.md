# Voice examination: implementation and validation boundaries

PR #178, branch `feat/voice-examination-review`. Disabled by default with
`VOICE_EXAM_ENABLED=0`. No main merge, deployment, database migration, or new
provider key. `GEMINI_API_KEY` is required; extraction/final review use
`VOICE_EXAM_GEMINI_MODEL` or `DENTAL_CLINICAL_AI_MODEL`, default Gemini Flash Lite.

## Complete review lifecycle

1. The dashboard entry leads to owner-scoped patient search or anonymous patient
   creation. Selecting a patient does not start the microphone. The entry supplies
   the authenticated user to the shared application shell.
2. Explicit consent precedes audio/text processing. Live PCM streaming, 90-second
   manual clips and manual clinical text remain available. Interim transcription
   is display-only. Only finalized segments enter clinical extraction.
3. Structured clinical context is cumulative and bounded at 24 KB, with nine
   3,000-character clinical fields, bounded tooth findings and appointment
   utterances. Full prior transcript and coaching are not context properties.
   Omitted fields/findings survive; explicit, quotation-supported retractions can
   remove mistaken fields/findings. New negative statements are retained as
   statements, not converted into missing data.
4. Extraction requests natural/implicit complaint interpretation, negation,
   speaker uncertainty, explicit clinician findings and plans. Short, anchored
   follow-up questions cover the whole examination rather than medications alone.
   `CLARIFY_NOW` means conversational clarification priority, not emergency triage.
   Coaching and decision barriers accumulate transiently, bounded at 24 items.
   Hints about fear/cost/time/trust may yield limited observations and questions;
   the model must not infer a personality, diagnosis, hidden motive or sales lead.
5. A clinician can explicitly load previous clinician-approved voice clinical
   notes, verify their current relevance with the patient, and add them to context.
   Only systemic-history, medication and allergy sections from the last 12 saved
   voice analyses are loaded; arbitrary narrative records are excluded. This is
   not a complete longitudinal medication reconciliation system. Different
   historical/current statements are displayed as unresolved, not silently merged.
6. During the conversation the existing extraction call handles complaints,
   findings, questions and communication feedback. No parallel automatic clinical
   model call or source download is started for each segment. The normal flow
   performs one whole-examination final review on Finish. A separate, collapsed
   optional clinical-check button is available only on explicit clinician demand.
7. Live Finish flushes audio and waits for pending extraction before requesting
   one final Gemini review. Manual clip/text users have an explicit final-review
   button. It covers summary, clarification questions, contradictions and
   source-grounded clinical considerations. No second model is introduced.
   Same-context successful final reviews are reused in the browser. Failed,
   truncated, stale or pending reviews do not unlock the normal save workflow.
   A new recording, new unprocessed text, changed field or appointment details
   invalidates the final review. Clinician edits are preserved across extraction.
8. The clinician selects fields/findings and confirms after final review.
   Existing profile fields, a clinical-note analysis and optional calendar event
   are updated atomically. Coaching, complete transcript, checklist and source
   quotations are not save properties. Save remains an owner-authenticated manual
   clinical editing operation; the final-review UI is not a cryptographic server
   attestation of AI correctness. Optimistic revision checks include patient
   identity/age/birth date/complaint, tooth state and latest analysis. Idempotency
   prevents a second record for the same request key.

## Calendar

Dates are resolved by application code, never a model-invented timestamp. One
explicit date or an unambiguous relative day, one time and explicit acceptance
can prefill a reviewed appointment. Clearly qualified spoken hours such as
“yarın öğleden sonra saat üçte” and 24-hour spoken times are supported. “Saat
üçte” without a time-of-day qualifier stays unresolved. Cancellation, alternative
times and uncertain acceptance require clinician completion. Existing weekly
occurrences are checked. Voice bookings serialize by owner; unrelated calendar
routes do not share that lock, so this is not a system-wide exclusion constraint.

## Public clinical corpus

Six fixed ADA documents are available: diabetes, prophylaxis,
anticoagulants/antiplatelets, osteoporosis medicines/MRONJ, pregnancy and hypertension. Fetches use fixed
URLs, reject redirects, bound input and cache document-only excerpts for one hour.
No patient query is sent to these sites.

`app/data/voice_drug_sources.jsonl` contains **eight actual public DailyMed SPL
labels**, downloaded and parsed from the official NLM service: amoxicillin,
ibuprofen, metronidazole, warfarin, acetaminophen, lidocaine, fluconazole and
clindamycin. Source IDs, label versions, effective dates, retrieval timestamps,
product names and clinical sections are preserved. Spelling aliases are explicit;
unverified Turkish brand equivalences are not inferred. These are US,
product/formulation-specific labels, not Turkish approvals or interchangeable
formulations. They are a starter corpus, not all drugs or a comprehensive DDI DB.

`scripts/import_voice_drug_labels.py` imports public SPL XML, individual ZIPs and
nested label ZIPs from the official full/periodic archive offline, without an LLM
or credentials. It rejects oversized XML/entities, preserves complete table rows,
updates by source identity/version and writes atomically. Example:

```sh
python scripts/import_voice_drug_labels.py downloaded-spl.xml --output app/data/voice_drug_sources.jsonl
```

`VOICE_EXAM_DRUG_CORPUS` can point to an operator-maintained corpus. The current
loader bounds it at 64 MB/10,000 records; a larger full-label archive needs a disk
index rather than increasing web-process memory without review. Corpus lookup is
local and token-bound. Only a bounded selection of paragraphs/documents is sent
to the model. Turkish TİTCK KÜB/KT bulk collection is **not implemented**; the
official index was verified but no Turkish corpus is claimed. Restricted SDCEP
commercial content was not copied.

Clinical output requires exact patient-value and source-excerpt anchors; invented
citations are discarded. Text extraction anchors are additionally checked against
submitted source text/prior structured anchors, not only the model's transcript.
This proves quotation membership, not clinical correctness or complete coverage.
Unknown/missing evidence never means safe. Source dates and formulation/country
limitations remain available. No automatic diagnosis, prescribing or medication
changes occur.

## Live transport and privacy

The authenticated owner-scoped WebSocket checks exact Origin and consent before
provider connection. API keys stay in server headers. Default live model is
`gemini-3.5-transcribe-live`; `VOICE_EXAM_LIVE_MODEL` can override it.
`VOICE_EXAM_LIVE_ENABLED=0` disables Live independently. AudioWorklet supplies mono
PCM16/16 kHz in bounded 100 ms packets with tail flush. Backpressure, disconnect
and page backgrounding stop or pause audio; no automatic paid reconnect/replay.
The browser pauses after nine minutes, before the documented ten-minute
Transcribe Live limit; the proxy bounds its connection at 570 seconds. Explicit
restart retains the processed clinical context. Four streams/one per owner are
process-local limits, not distributed admission control. Live transcription does
not supply verified speaker diarization; ambiguous attribution requires review.

Application audio is memory-only. Pagehide, successful save and draft clearing
remove transient text, coaching, final results, historical fields, inputs and
audio references, abort requests and close resources. This is reference cleanup,
not guaranteed physical memory erasure or cancellation of provider processing.
No transcript/audio/coaching is put in generic WorkJob payloads.

Private-life minimization is requested from the model; it is not a proven
semantic privacy filter. Clinician-selected free text still needs review. Raw
audio reaches Gemini before text minimization. Provider retention, account terms
and operational logging remain to be verified before real-patient use.

## Validation

81 focused Python tests pass, including ownership/consent, atomic save,
idempotency, optimistic chart revision, original-text evidence, explicit
retractions, final review/truncation, historical-record scope, source import,
table preservation, corpus matching, XML safety and rendered templates.
Five actual-controller Node harnesses pass: cumulative review/minimal save,
finalization drain/failure/retry/edit invalidation/cleanup, Live lifecycle and
16/44.1/48 kHz PCM resampling/tail flush. Python compilation and JS syntax pass.

No Gemini credential is available locally. Provider transport/answers in tests
are mocked. Real Gemini authentication, clinical-language accuracy, actual
microphone/browser compatibility, full source coverage, speaker attribution,
alert latency and retention have **not** been established. These are validation
boundaries, not completed capabilities. Keep the feature disabled pending them.

## On-demand sources and actual-device verification (follow-up)

A comprehensive local medication archive is not a prerequisite. Extraction now
returns up to six quotation-anchored, validated English generic ingredient search
terms. Only those short terms, not patient statements/identity or full context,
are sent to the fixed official DailyMed service. On demand the server fetches a
matching generic label, validates its SPL identity, parses the actual XML,
retains version/date/formulation/jurisdiction and sends bounded evidence into the
existing final Gemini call. Model-provided URLs, combination substitution,
redirects, oversized documents and malformed identities are refused. Up to three
terms are looked up per review; excess/failed terms are explicitly reported as
uncovered, never cleared. Document-only results are cached for one hour, at most
128 entries. Existing starter labels remain a fallback; no additional bulk corpus
was downloaded for this change. Official live lookups for naproxen and amoxicillin
were actually performed successfully. This verifies source access, not clinical
accuracy. Pregnancy and hypertension ADA pages were also verified and added, so
source selection is not limited to medication topics.

The authenticated `/voice-exams/device-check` page tests the current device's
microphone and the same PCM worklet locally, shows a signal result, shuts down
after six seconds, and stops on backgrounding, navigation or late permission.
It records nothing and sends no audio to a provider/server. It does not prove
Gemini connectivity or clinical speech recognition. A person must run it on the
actual phone; the cloud environment cannot certify that microphone.

`python -m scripts.check_voice_provider --run-paid-checks --live` is an explicit,
synthetic-only real-provider smoke check using the environment's existing Gemini
credential. It performs extraction, final review and optionally the Live
handshake, printing pass/fail codes only. It never reads patient records. This
workspace has no Gemini credential: the command returned
`OPT_IN_OR_PROVIDER_CREDENTIAL_MISSING`; no real-model success is claimed.

Follow-up validation: 81 focused Python tests and five controller/worklet Node
harnesses. Real-device execution and the credentialed provider check remain
operational checks, not mocked-test claims. GitHub Actions failures on the prior
commit returned no job steps/logs; the annotations endpoint is unavailable through
the connector, so the failure cause remains unverified. Do not equate local tests
with a successful full repository CI run.


## Final workflow simplification

The normal path is patient selection/consent → conversation and cumulative
extraction → Finish and pending-segment drain → one whole-examination final review
→ explicit clinician selection/confirmation → atomic save → patient file with a
save acknowledgement. A phase indicator makes this visible. Earlier communication
observations remain available in the final results; clarification questions can
be marked resolved, and changed clinical information invalidates the final review.
There is no automatic parallel `/clinical` request per segment and identical final
reviews are reused. Source fetching is bounded evidence retrieval, not a second
interpretation engine or a new bulk medication project.

Manual audio clips put their bounded 24 KB context in the binary POST body
instead of oversized proxy headers; legacy raw-audio clients still work. Invalid
packet lengths are rejected before provider calls. No temporary audio files are
introduced. Tests cover the packet path and the absence of automatic parallel
clinical calls, cached final-review reuse, retained communication feedback and
phase progression. Main and production remain untouched.
