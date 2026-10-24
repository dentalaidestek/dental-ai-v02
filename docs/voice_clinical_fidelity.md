# Clinical fidelity repair
Audio files now use Gemini only for transient clinical transcription, followed by Claude for extraction. Text/live transcript input goes directly to Claude extraction. Final source-backed review remains one separate Claude call. Thus audio import adds one semantic extraction request compared with the former combined Gemini call; live/text input replaces Gemini extraction rather than duplicating it. Existing concurrency and provider budgets remain.
The extractor returns bounded atomic clinical facts, each with one exact input quotation and a current/historical/planned/negated/unknown label. These are folded into existing clinician-editable clinical fields, with no new automatic patient writes or raw transcript persistence. Facts with unsupported quotations/categories are discarded; overlong fields fail explicitly instead of silently truncating.
The displayed transcript is the supplied clinical text rather than Claude's rewritten transcript. Formatting-only quotation recovery preserves original word/numeric tokens. This cannot recover inaudible speech or guarantee completeness.
A tooth CARIES candidate requires explicit non-negated caries wording; non-restorability alone cannot create it. Other tooth statuses retain their existing checks.
Natural spoken acceptance such as same-day "beşte" may agree with an explicit17:00 proposal. Different days/hours, explicit morning conflicts, negation and ambiguous proposals remain rejected.
Consent now names Gemini transcription and Claude extraction/final review.
Validation:158 focused Python tests passed, including atomic medication/lab/plan preservation, fabricated fact rejection, caries false-positive rejection, colloquial appointment acceptance/negative cases, text-only Claude routing and prior permission/record safeguards. Final browser lifecycle Node harness passed.
The October 24 live follow-up is recorded in voice_clinical_fidelity_live_result_2026-10-24.md. No unit test establishes overall clinical accuracy, semantic correctness of source entailment, or acoustic intelligibility of the synthetic recording.


## Live follow-up, 2026-10-23
Claude extraction now uses a strict data tool with atomic clinical facts and separate identity fields; duplicate clinical summaries and model-rewritten transcripts are omitted from its contract. Final summaries are exact reviewed field values, preventing a second paraphrase from reversing a negation. Source-backed clinical review remains one separate request.
The English antiresorptive topic identifier now selects its existing ADA document, alongside common osteoporosis/history terminology. This is source routing, not an automatic risk diagnosis.
The calendar parser accepts numeric Turkish suffixed hours (17’de/5’te), rejects conflicting hours/morning/day/cancellation, and tolerates trailing non-calendar speech without ignoring later corrections.
Specific tooth candidates now require their FDI number, numeric or spoken Turkish, in the exact quotation. Region-only mentions cannot establish a tooth number.
Original Google-generated synthetic audio contained byte-identical chunks for different intended utterances; its acoustic completeness results are inconclusive. A new 60-second local Piper recording has 25 distinct utterance waveforms, pitch-distinguished roles and a defined 26dB SNR/echo simulation. It is synthetic, not a physical microphone-distance test. See the separate live result report for observations and remaining limits.

## October 24 extraction and review corrections
A single canonical atomic-fact prompt replaces conflicting legacy summary instructions. Successful transport logs only candidate/grounded counts; long clinical speech without grounded fields has an explicit incomplete notice.
Medication values preserve quoted speech verbatim. Source-request terms must occur in the quoted speech (including carried context); this prevents unsupported active-ingredient substitutions but reduces automatic US-label lookup for translated names. This change is not a verified product/ingredient resolver.
Final contradiction items require two distinct, grounded field quotations and show both. Instructions distinguish other-disease denials, daily versus intermittent use, historical exposure and missing information. Two quotations do not prove semantic contradiction; clinician review remains necessary.

Private communication, decision-barrier, follow-up and topic quotations now recover original spans across formatting-only changes, using the same consecutive word/number validation as clinical facts. This does not accept paraphrases, number translations or fabricated quotations. Content-free accepted/candidate counts support diagnosis without logging speech.

Patient concerns now also use the atomic fact contract (patient_concern), routed solely to temporary private coaching. They do not enter selectable clinical fields or carried clinical context. This avoids a separate model call and addresses observed zero-candidate legacy insight arrays.

The patient_concern fact kind routes stated fear/expectations to temporary private coaching, never patient fields or carried clinical context. The October24 live run produced one such private insight after reprocessing the unchanged speech transcript; exact drug-name recognition and temporal categorization remained partial.
