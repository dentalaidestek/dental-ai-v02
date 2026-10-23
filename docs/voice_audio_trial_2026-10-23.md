# Real provider audio-file trial, 2026-10-23

Production version: 2731fd7b2145bfb90680fd6f7285031ae90e136d (PR 183).

Input: 60.0-second synthetic Turkish patient/clinician dialogue, 110 words, two pitch variants of Turkish speech synthesis. Simulated distant capture: -12.51 dBFS peak, -29.44 dBFS RMS, 22 dB SNR background noise, low-pass filtering and three short room echoes. This is not a physical-distance or live WebSocket/microphone test.

Uploaded through the actual consented audio file UI to the existing authenticated audio route, not as text. Audio processing and final review both visibly completed. No selected fields were saved to the patient record. The synthetic draft was cleared after inspection.

Observed outputs:
- Right-lower cold/nocturnal pain extracted. Three-day duration remains in the evidence quote, absent from the complaint value.
- Patient-reported diabetes and metformin extracted.
- Unnamed antibiotic rash retained; clarification question generated.
- Existing filling on 45 extracted; uncertain caries on 44 was not converted into a confirmed tooth status.
- Fear and cost barriers extracted with transient clinician suggestions.
- Appointment proposal retained, but agreed next-day 15:30 was not resolved into an accepted scheduled date.
- Explicit imaging/conditional treatment plan was not extracted into the plan field.
- Recognized speech included errors: 'kanal' became 'kanat', and 'soğuk su içince' became 'soğuk su ince'.
- Final summary only summarized the appointment proposal, omitting the other extracted clinical fields. Source-grounded clinical items were empty; no safety assurance follows.

The successful extraction result was observed 23.733 seconds after file selection began. This is an upper-bound UI observation including upload and automation overhead, not isolated provider latency or a percentile. Log retrieval failed with a Render log-service 503, so no server timing claim is made.

Conclusion: actual audio transport and provider processing worked for this fixture. Extraction/final-summary completeness and everyday-language appointment resolution remain failing criteria. The trial does not establish live-stream continuity, clinical correctness or physical microphone performance.
