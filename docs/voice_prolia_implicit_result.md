# Implicit Prolia/extraction live challenge — 2026-10-23

## Scope
Frozen protocol and dialogue are in the preceding commit. Published case inspiration and independent ADA reference are listed there. This is a fictional adapted pre-extraction consultation, not the source patient's actual recorded conversation.
PR188 remained open/unmerged at trial time. The live endpoint used the existing Gemini implementation; no Claude result is claimed. No code, prompts, fields or source payload were changed for the audio baseline.

## Inputs and separate independent review
130-word Turkish doctor/patient dialogue. The patient's current injection is named by brand only, without saying denosumab or MRONJ. It includes historical oral osteoporosis medication, dose/schedule, a tooth46 extraction PLAN, fear and a mutually accepted same-day17:00 review.
Independent expected interpretation BEFORE looking at results: investigate the antiresorptive/extraction healing risk with patient-specific source support, verify the medication card and schedule/history, do not diagnose existing MRONJ or universally forbid extraction/stop the medicine. Preserve medication history, fear and the review appointment.
Synthetic audio with digital distant-acoustic simulation: PCM60.0s, MP3 container60.048s, 961197bytes, SHA25696adb97f2b1459a8335e3f46fa9de5df64d86805bef0b6cfa15e00c217419455.
This is an audio-file processing test, not physical microphone/WebSocket testing.

## Actual audio baseline
The returned transcript omitted the Prolia brand, past Bonviva/risedronate sentence, four-month timing, age, fear and appointment clauses. It also misheard the opening tooth complaint, although the structured complaint reasonably reconstructed dental meaning.
Structured fields preserved osteoporosis, a60mg six-monthly injection, tooth46 findings and planned extraction. No named current/past drugs, age or appointment were presented. No tooth was falsely marked extracted.
The final review displayed one MRONJ reminder connecting antiresorptive use with extraction, possible clinician coordination and missing drug timing/history. It asked for the exact injection identity rather than asserting a confirmed denosumab diagnosis from dose alone.
UI reported9 sources. Server log2026-10-23T09:54:23.753759216Z: voice_final sources=9 accepted=1 rejected_reasons={}.
Shown supporting publication: Cochrane review PMID35866376. The displayed excerpt supports the medication/MRONJ association, but does not by itself establish every suggested alternative or management detail. In particular the generic conservative-treatment alternative needs care given the stated non-restorability; exact-substring checks do not prove semantic entailment.
No blanket extraction ban, automatic drug holiday or current MRONJ diagnosis appeared.
Judgment: risk recognition PARTIAL SUCCESS; medication fidelity, fear and appointment FAIL. Overall end-to-end challenge FAIL.

## Separate diagnostic text control
After documenting and clearing the audio draft, entered the SAME source dialogue as text, with no expected answer/source excerpt/rubric added. This is an additional diagnostic run, not an edited baseline or a replacement pass.
Age62, complaint, osteoporosis, allergy answer, tooth46 and extraction plan survived. Fear was recognized with empathetic communication suggestions.
Despite all named medications being explicit in the input, NO medications field was displayed. The final review therefore asked whether an antiresorptive was used and its dose rather than using already supplied details.
A source-backed conditional MRONJ reminder was displayed, but anchored only to osteoporosis.
The proposal TODAY17:00 and acceptance TODAY at five appeared in the appointment draft; start time remained blank and calendar-selection unchecked. Final prose could say17:00 while deterministic schedule resolution could not complete.
UI reported12 sources. Server log2026-10-23T09:56:49.789713181Z: voice_final sources=12 accepted=1 rejected_reasons={}.
Judgment: loss is not limited to audio recognition. Extraction/normalization can discard medication information even with correct text; this trial does not establish which of those two stages removed it. Appointment natural-language acceptance also needs repair.

## Limits and cleanup
One example per input mode, no sensitivity/specificity estimate. Risk association detection is not complete clinical correctness. No actual patient fields, tooth chart or appointment were saved. Both transient drafts were cleared and cleanup success was visibly verified.
Screenshots and UI snapshots retained in scratch only; no screenshot added to Library. MP3 deliverable saved separately.
