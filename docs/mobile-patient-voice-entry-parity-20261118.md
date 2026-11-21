# Patient profile / voice-exam navigation parity — 18 November 2026

## Web-first comparison

The web patient detail page (`app/templates/patient_detail.html`) exposes the patient actions Diş Şeması, AI Analiz, Randevu and Tedavi, plus Uzman Danış. It includes the approved voice-history data but does not add a “Sesli Muayene” start action to the patient profile.

The native app already has a dedicated home feature card and a separate `VoiceExam` stack route. However, `NativePatientProfile` also rendered an extra “Sesli Muayene” button under Dental AI and received a `voice` navigation callback from `PatientDetailScreen`. This duplicated the entry and contradicted the agreed separate-page flow.

## Change

- Removed the voice-start button and its callback from the patient profile.
- Kept the dedicated Home `VisualFeature` and `VoiceExam` stack screen unchanged.
- Kept the approved-only patient voice-history section; it is patient data, not a recorder entry.
- Updated patient-profile UI regressions to assert that no voice-start button is present on the patient profile and that the dedicated Home feature and route remain registered.

No voice session, patient history, clinical record, API, or server behavior changed.
