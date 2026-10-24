# Voice examination live regression — 24 October 2026

## Release and method

Production: https://dentalai.tr. Final code: `7ec4f2cf13ff1ab098d9c9d123294ad1baaaab4c` (PR204), Render deployment `dep-dbe48acs728c738bveg0`, live at 05:39:19 UTC / 08:39:19 Türkiye time. PR200–204 were merged and automatically deployed; no duplicate manual deploy was triggered.

The same fictional implicit antiresorptive/extraction consultation was used throughout. The original frozen protocol is `voice_prolia_implicit_protocol.md`. It is an adapted pre-extraction dialogue inspired by PMC4377652, not a real patient's verbatim consultation. The expected risk interpretation was not added to the submitted speech or clinical fields. This reused development regression is not a blind accuracy benchmark.

Corrected audio: `local-dialogue-60s.mp3`, SHA256 `13340d2d1e61e63b80beaabccad495009bdf58a39a4f850835f69407cbcb57fc`. The PCM is exactly 60 seconds, 130 words, generated locally with Piper Turkish dfki-medium, 25 distinct utterance waveforms, pitch-distinguished roles, 26dB SNR and a defined echo/filter simulation. It is not a physical microphone-distance test or independent confirmation of every intended pronunciation.

The older Google-generated fixture contains byte-identical audio for different intended utterances (including turn13/14,15/16,17/18,21/22). Its completeness failures cannot be attributed solely to speech recognition. Do not treat those old audio comparisons as validated accuracy measurements.

The full corrected audio was uploaded on PR203. After PR204 became live, its unchanged machine transcript was reprocessed through the visible text control, then the final review was run. No manual transcript correction, expected drug name, risk answer or clinical-field edit was supplied. Therefore the last observation validates the PR203 audio stage plus the PR204 extraction/review stages, rather than a fresh audio upload on PR204.

## Observed behavior

| Check | Observation | Result |
| --- | --- | --- |
| Clinical numbers | Tooth46, age62, 60mg, six-month interval and four-month elapsed time survived the latest audio transcript. | Preserved in this run |
| Exact drug names | Risedronat became hisedronat; Prolia became prolya. Other repetitions produced hisse dronat/prolo. | Not reliably transcribed |
| Drug identity | Final medication values retained the spoken spelling; the earlier erroneous etidronat expansion was no longer inserted. The final checklist requested product/ingredient confirmation. | Guard observed |
| Temporal interpretation | Historical oral drugs and injection details survived, but current/historical labels for the injection and last dose remained inconsistent. | Partial |
| Clinical fields | Final reprocessing reported12 fact candidates and6 grounded clinical fields; identity and appointment were separate. | Fields produced |
| Tooth chart candidate | Tooth46 was OTHER, backed by its explicit numbered finding. No unspoken CARIES or completed EXTRACTED state appeared. Nothing was applied to the chart. | Guard observed |
| Appointment | Quoted17:00 proposal and spoken5 o'clock acceptance resolved to24 October2026,17:00 Europe/Istanbul. The program checkbox was checked in the draft. | Draft only; no calendar record saved |
| Fear/expectation | The fear and wish to finish today appeared as private coaching after patient_concern routing. The physical chief complaint did not include this concern in the final reprocessing. | Private insight produced |
| Final summary | The negative finding that the tooth was not suitable for filling remained negative; the app displays the reviewed values directly. | Preserved |
| Source-backed reminder | The final review linked extraction and prior osteoporosis medication exposure to an ADA MRONJ control point, with a source excerpt and link. It requested confirmation of uncertain drugs and dates. No blanket extraction prohibition or automatic drug cessation was shown. | Reminder produced |
| Contradictions | The earlier false other-disease contradiction did not appear in the final run. Two grounded quotations are now required by the contract. | No contradiction shown in this run |

Final runtime log: `voice_final sources=3 accepted=4 rejected_reasons={}`. All three supplied references visible in this run were ADA professional documents (osteoporosis/MRONJ, restorative treatment, acute pain). This does not demonstrate successful PubMed or DergiPark evidence retrieval for this case. Four accepted items mean their configured quotation checks passed, not that four clinical conclusions were independently validated. Source-to-claim entailment remains a clinician/reviewer responsibility; literal quotations alone do not establish it.

The private insight log showed communication1/0 because the accepted item came from a patient_concern atomic fact, while the denominator counts the legacy communication array. It is not an acceptance percentage. Legacy communication, barrier and in-conversation-question arrays were repeatedly empty even with explicit concern in the transcript. The atomic concern route repaired the displayed private insight in this case; broader recall has not been established.

## Changes and validation

- PR200: one canonical atomic extraction prompt, safe candidate/grounded counts, explicit empty-clinical-output notice.
- PR201: medication values preserve quoted speech; automatic lookup terms must occur in their quotation, including carried context. This reduces lookup coverage for translated generic names and brand-to-ingredient expansion; it is not a verified drug-identity resolver.
- PR202: two distinct grounded statements required for a contradiction; scope/temporality instructions distinguish missing information from conflicting claims.
- PR203: formatting-only quote recovery extended to private insights and source/topic quotations. Word or numeric substitutions and fabricated quotations remain rejected.
- PR204: patient concerns share the atomic extraction contract but route only to transient private coaching, not selectable patient fields or carried clinical context.

Local verification:158 focused Python tests passed; the Node final-review lifecycle harness passed. These exercise permission/record safeguards, fact grounding, temporal preservation, explicit tooth evidence, appointment resolution, private-concern routing, source identity and failure behavior. No hosted-CI success, live concurrency benchmark or60,000-user capacity claim is made.

Timing observations are UI polling bounds, not precise latency measurements: an audio draft was visible by approximately31seconds in one run; final text reprocessing was visible by29seconds; the last source-backed review was visible by73seconds. Cold network retrieval and the free service's wake-up period affect these observations. No live stress test was performed in this continuation.

## Disposition

The flow executes and the targeted source-backed reminder, appointment draft, explicit tooth guard and private concern are visibly present. The strict original accuracy challenge remains **PARTIAL**, principally because exact medication transcription and temporal categorization are not reliable. Some final questions also ask to reconfirm information already present; broader clinical accuracy and complete recall are unproven.

No Save/Apply action was clicked. The final draft was cleared through the visible control and the page confirmed that temporary consultation data was cleaned. Screenshots were captured before cleanup. Their local paths are `/workspace/scratch/voice-source-card-20261024.jpg` and `/workspace/scratch/voice-concern-appointment-proof-20261024.jpg`.
