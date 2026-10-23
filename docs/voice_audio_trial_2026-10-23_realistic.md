# Realistic voice audio trial — 2026-10-23

Production releases: PR184 d51f569ba6055dbe5140e8c1193358f0d1e4a401 (deploy dep-dbdfasjm8hqs73e8csq0), followed by PR185 0fdf394cf41464b28bdaebbd78e26598f38cea6a (deploy dep-dbdfdvk9v7es73dthb6g). Both reached live. The initial deployment produced a transient 502; the subsequent page load succeeded.

## Input
105-word fictional Turkish doctor/patient dialogue, synthesized with two pitch variants. Definite deep caries in tooth44, existing filling in45, radiograph and vitality assessment before deciding restoration versus endodontic treatment. Diabetes/metformin, unnamed-antibiotic rash, needle fear, financial concern, and explicitly repeated next-day15:30 acceptance.
Synthetic distant-room effect: lowpass3400Hz, echoes43/91/163ms,22dB SNR. PCM60.0seconds; MP3container60.048seconds,961197bytes. SHA256 84be27659da00ef2d7c5e2b120aeeb1fc5ff3fb8e15479b92c27f4099e3590e4.
This is actual audio submitted to production Gemini, not text-only/mocked-provider testing. It is not a physical microphone/distance or continuous WebSocket test.

## Trial outcomes
- Both runs correctly extracted complaint duration/cold/night features, diabetes, metformin, unnamed antibiotic reaction,44caries,45filling, and the conditional diagnostic/treatment plan. The new recording did not exhibit the earlier kanal→kanat error.
- First final review received4sources but discarded every generated clinical item. PR185 removed competing original speech quotes from final clinical-field input, reinforced original-language verbatim source quotation, and retained exact validator checks. Count-only rejection diagnostics were added.
- Repeated final review displayed all clinical summary fields, questions about the unidentified antibiotic and diabetes control, and a source-backed diabetes-related reminder linked to ADA Diabetes.
- Production log: voice_final sources=4 accepted=1 rejected_reasons={}.
- Sources visibly supplied: ADA pain guideline, ADA restorative caries guideline, ADA Diabetes, and DailyMed metformin label. No eligible PubMed/DergiPark article was shown in this trial; partial/unavailable coverage remained visible. This does not establish exhaustive literature review or clinical correctness.
- Calendar parsing unit cases now handle natural repeated day/time acceptance, but the actual repeated audio trial STILL did not populate the datetime control. The final language summary understood15:30. End-to-end appointment automation remains unresolved; do not claim it passed.
- Communication coaching detects fear/cost; some observations/suggestions remain duplicated across communication/barrier sections.
- Observed completion bounds (not provider latency): repeat audio result seen within36.1seconds; repeat final result seen within32.2seconds. Observation gaps include automation/model/tool work.
- No Save/apply click, tooth-chart write, or appointment creation. Both drafts cleared through UI; final cleanup message confirmed.
-102 focused Python tests and7 browser harnesses pass locally. GitHub hosted workflows fail without executing steps, including the prior main baseline; hosted-CI pass is not claimed.

The screenshot and audio were made available to the user. Remaining concerns: unresolved calendar materialization, limited literature coverage, duplicated coaching, and lack of physical/live-stream testing.
