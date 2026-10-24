# Natural dialogue contraindication test — 2026-10-24

Guideline-based fictional dental case, not a published patient's history. Expected outcome defined before the live run: identify current simvastatin and proposed clarithromycin; warn the clinician that coadministration is contraindicated, with source support. If clarithromycin is essential, medication interruption must be clinician-managed. No automatic drug cessation or patient-record writes.

Primary references: NHS SPS Managing interactions between macrolides and statins; current SDCEP Dental abscess / Second line antibiotics; GDC Communicate effectively with patients. Clarithromycin is a contemplated second-line option after completed first-line treatment and review, not a routine first-line recommendation.

Audio: locally generated Turkish Piper dialogue, 26 turns, 183.898 seconds, 22 dB nominal background-noise SNR plus discrete non-speech transients, low-pass and short echo; imported as 80.813, 78.387 and 24.699 second chunks. SHA256 5e535f90ea0d01a952dc575e16b12aa53f6c03348cd9423df9e9800b00ce930d. Synthetic acoustic test, not a physical microphone or spontaneous human speech test.

Baseline production commit 7ec4f2cf13ff1ab098d9c9d123294ad1baaaab4c: simvastatin 20 mg accurately transcribed in chunk 1. Chunk 2's 'Başka ilaç yok' replaced the previous medication field. Full review received two sources and did not report the expected interaction. Communication captured fear, time, cost and understanding concerns, but was not separately appraised against a communication source. Appointment acceptance was misheard as 'yarın ikili gelebilirim'; app correctly left the date/time unresolved instead of guessing.

Repairs: accumulate clinical facts across audio chunks unless explicitly withdrawn; preserve and merge anchored source requests; permit bounded spelling/transliteration hypotheses for official-label search without changing the quoted medication; mark name resolution unconfirmed until clinician verification. Existing final Claude call now receives short transient communication anchors plus a selected GDC professional standard. Added SDCEP interaction and SPS macrolide/statin documents to bounded topic routing. This expands source coverage, not a comprehensive interaction database or case-specific alert rule.

Validation: 169 focused Python tests and Node final lifecycle harness passed before release. Live post-release retest pending; do not infer success from unit tests or deployment alone. All live test drafts cleared without Save/Apply.
