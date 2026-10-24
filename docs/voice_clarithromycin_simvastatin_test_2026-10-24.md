# Natural dialogue contraindication test — 2026-10-24

Guideline-based fictional dental case, not a published patient's history. Expected outcome defined before the live run: identify current simvastatin and proposed clarithromycin; warn the clinician that coadministration is contraindicated, with source support. If clarithromycin is essential, medication interruption must be clinician-managed. No automatic drug cessation or patient-record writes.

Primary references: NHS SPS Managing interactions between macrolides and statins; current SDCEP Dental abscess / Second line antibiotics; GDC Communicate effectively with patients. Clarithromycin is a contemplated second-line option after completed first-line treatment and review, not a routine first-line recommendation.

Audio: locally generated Turkish Piper dialogue, 26 turns, 183.898 seconds, 22 dB nominal background-noise SNR plus discrete non-speech transients, low-pass and short echo; imported as 80.813, 78.387 and 24.699 second chunks. SHA256 5e535f90ea0d01a952dc575e16b12aa53f6c03348cd9423df9e9800b00ce930d. Synthetic acoustic test, not a physical microphone or spontaneous human speech test.

Baseline production commit 7ec4f2cf13ff1ab098d9c9d123294ad1baaaab4c: simvastatin 20 mg accurately transcribed in chunk 1. Chunk 2's 'Başka ilaç yok' replaced the previous medication field. Full review received two sources and did not report the expected interaction. Communication captured fear, time, cost and understanding concerns, but was not separately appraised against a communication source. Appointment acceptance was misheard as 'yarın ikili gelebilirim'; app correctly left the date/time unresolved instead of guessing.

Repairs: accumulate clinical facts across audio chunks unless explicitly withdrawn; preserve and merge anchored source requests; permit bounded spelling/transliteration hypotheses for official-label search without changing the quoted medication; mark name resolution unconfirmed until clinician verification. Existing final Claude call now receives short transient communication anchors plus a selected GDC professional standard. Added SDCEP interaction and SPS macrolide/statin documents to bounded topic routing. This expands source coverage, not a comprehensive interaction database or case-specific alert rule.

Validation: 169 focused Python tests and Node final lifecycle harness passed before release. Live post-release retest pending; do not infer success from unit tests or deployment alone. All live test drafts cleared without Save/Apply.

## Post-release observation (PR205)

Commit 9ae52b1199044db7caed6d56b605dc8e010e775f, Render dep-dbe5696i0phs73bnsh90 live 06:43:10 UTC. Same three unchanged audio files processed: simvastatin survived chunk 2 and the full review explicitly produced the NHS SPS-supported clarithromycin/simvastatin contraindication plus clinician-managed interruption consideration. Six sources were supplied; this count is not a correctness metric. GDC-supported cost and communication items appeared. A doctor stop-signal explanation was not carried into final communication context and was incorrectly requested again.

A text-only negative control changed simvastatin to rosuvastatin in the complete authored dialogue. Claude quoted the correct SPS statement that rosuvastatin can be continued, but added a non-applicable simvastatin caution and a generic SDCEP statement whose referent list was absent. This is a partial negative-control pass, not a clean pass. No records saved.

Follow-up: include grounded doctor responses and patient teach-back as transient atomic communication facts; exclude them from patient fields. Strengthen final review against unrelated-drug alerts and missing-referent excerpts. Keep spelling-candidate uncertainty even when the warning cites a different professional guideline. Resolve harmless comma-separated work-leave tails in appointment acceptance; preserve conflicting/cancelled/unclear time rejection. 172 focused Python tests passed, plus final targeted review tests after the prompt update. Follow-up live verification pending.
