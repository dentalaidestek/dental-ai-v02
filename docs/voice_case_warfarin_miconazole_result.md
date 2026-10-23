# Published-case audio trial — 2026-10-23

Baseline production commit: 8403b85add418430796f4424adb8098f045de23c.
Protocol frozen in preceding commit before submission. No application code or prompt changes for this trial.

## Input
Published case: PMID11068529, https://pubmed.ncbi.nlm.nih.gov/11068529/ .
Independent expected interaction: MHRA oral miconazole/warfarin warning (URL in protocol).
Fictional pre-exposure Turkish consultation, not verbatim source audio; 76-year-old on warfarin5mg/day, recurrent thrombosis, monthly INR2–3, oral candidiasis, proposed miconazole ORAL GEL not started.
Synthetic Turkish speech with digitally simulated distant acoustics; not a physical microphone/WebSocket test.
MP3 duration60.048seconds, 961197bytes; SHA25617239484f5be516f7ef61704d81d4a2afd83567277c6505dbc789c706784adee.

## Actual live result: FAIL
Submitted actual MP3 through production voice-exam audio upload; no manual field edits.
Transcript correctly retained both drug names, oral-gel formulation, planned/not-started status, dose and INR2–3.
Structured fields retained age76, complaint, thrombosis, Varfarin5mg and candidiasis. Plan was reduced to reviewing medication list/labs and finalizing treatment; proposed miconazole oral gel was omitted. INR2–3 was also not preserved in final structured fields.
Final review showed4 sources: ADA pain guideline, ADA antibiotic guideline, DailyMed warfarin, DailyMed Miconazole. Formulation of the latter was not independently inspected, so oral-gel applicability is unverified.
Patient-communication text mentioned the two-drug interaction generically. NO source-verified INR/bleeding warning was displayed.
UI: "Bu görüşme için kaynakla doğrulanmış kontrol noktası yok. Bu sonuç güvenlik onayı değildir."
Render log at2026-10-23T06:34:20.301750902Z: voice_final sources=4 accepted=0 rejected_reasons={"unknown_anchor":1}.
This establishes a rejected anchor and a missing planned drug; it does not establish the precise content of the rejected item.

## Interpretation
Predeclared criteria1 and2 fail. Generic advice to review medications is not adequate detection.
At least extraction preservation and patient-anchor handling need investigation. Do not weaken source anchoring or inject this expected answer merely to make the trial pass.
No global accuracy/sensitivity claim can follow from this single positive challenge.
No data were saved/applied to the real patient; draft cleared and cleanup success visibly verified.
