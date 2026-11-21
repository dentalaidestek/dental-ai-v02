# Native chat implementation and patient/tooth-chart parity audit

Compared against branch head `83d6f240dcd41f22e3c2d7f73dedc20472b4f91b`. This is a source comparison and local validation, not physical-device or authenticated-production acceptance.

## Implemented in this change

- Native PDF/audio document selection, camera/gallery images, attachment preview, protected download, OS file opening/sharing, and audio playback. Audio pauses when the app leaves the foreground. Cached downloaded/prepared documents are removed when their owning component is disposed. Playback does not request microphone permission.
- Native image annotation with pen colors, width, undo and clear; rendering exports a new JPG attachment while preserving the original. The same flow opens existing chat images and explicitly selected case images. Export keeps image aspect ratio and limits the longest dimension to 1600 pixels.
- Server upload adapter retains existing web case/message lifecycle handling, sanitizes images, checks PDF/audio signatures and limits documents/audio to 25 MB. Unsupported/spoofed uploads do not create messages. No upload is automatically retried after an uncertain response; users first refresh/check messages.
- Case-selected clinical images appear in the conversation through a case-link-scoped authenticated endpoint. It grants access only to explicitly linked media, not the patient's entire gallery. Outsiders, wrong links, removed messages and the user's deleted inbox state are rejected; responses use private/no-store.
- Fixed a regression in the previous request adapter: invalid consultation input again throws synchronously, preserving the established API/test contract. Existing tests were not relaxed.
- New patient form now includes the web's optional TC identity/address fields and handles the existing duplicate-patient response. Users can open the owned existing record or explicitly confirm creating a separate record. Repeated taps are guarded; uncertain creation requires checking the list before another attempt.
- Failed patient loading no longer uses the empty-list label; profile media-upload errors are visible and ask the user to check the server gallery before resending.

## Patient workflow comparison

Sources: `app/templates/patients_all.html`, `patient_new.html`, `patient_detail.html`, `app/main.py`, `app/mobile_api.py`, `mobile/App.tsx`, `mobile/src/api.ts`.

| Flow | Web | Native status after this change |
|---|---|---|
| Search/list/open | Owned patient records | Existing real API, pagination, refresh, virtualized list; device spinner remains unverified |
| Create/edit identity/contact/complaint | Name, birth date, phone, TC, address, complaint | Same fields now available; birth date still text input |
| Duplicate detection | Existing record / explicit force create | Now connected to the existing backend rule |
| Patient actions | Expert request, chart, analysis, appointment, treatment | Routes exist; request patient context preserved; appointment patient preselection still not consumed correctly |
| Clinical media | Typed multi-file upload and patient gallery | Existing single-image upload/separate gallery; full web multi-file/type/action parity incomplete |
| Analysis/voice history | Patient-specific analysis cards and voice review content | Patient detail does not render the equivalent history; explanatory anamnesis/voice sections are not persisted clinical records |
| Treatment records | History and clinical details | Existing real create/edit; rendering is less complete; dates remain text input |
| Delete | Owned server-side deletion | Existing confirmed delete; physical-device/account-isolation acceptance remains pending |

The web patient form does not establish separate persisted medication/allergy/systemic-disease fields. Do not invent those as completed native data merely because placeholder headings exist.

## Tooth chart comparison

Sources: `app/templates/tooth_chart.html`, `mobile/src/NativeToothChart.tsx`, tooth update/history handlers in `app/main.py` and mobile adapters.

| Capability | Comparison |
|---|---|
| Adult / primary FDI ordering | Same 32 permanent and 20 primary teeth, same upper/lower quadrant order |
| Tooth asset | Both use `enamel-atlas-v2.webp`; primary molars use molar column; lower jaw rotated |
| Status codes | Same HEALTHY/CARIES/FILLING/CROWN/ROOT_CANAL/EXTRACTED/IMPLANT/OTHER meanings |
| Surface identifiers | Same MESIAL/DISTAL/BUCCAL/LINGUAL/OCCLUSAL/INCISAL backend identifiers; native supports independent surface editing |
| Status appearance | Different: web overlays depict caries/filling/crown/canal/extraction/implant; native uses color markers and text/symbol replacements. Same base asset does NOT mean identical chart |
| Selected-tooth panel | Both have tooth information, clinical note and treatment/history sections; layout and interaction differ |
| History contents | Web history fetches surface status, treatment and analysis records; native treatment tab omits the equivalent analysis history and several displayed record details |
| Saving | Existing native APIs save real tooth/surface/treatment records and reload server data; save failure is displayed |
| Cross-device edits | No proven conflict-resolution contract; realtime refresh does not prove safe concurrent edits |

Conclusion: patient workflow and tooth chart are **not fully equivalent**. No new tooth-chart visual redesign is claimed in this commit. Next clinical work should connect patient/tooth analysis history, media parity and date/patient appointment selection before polishing the clinical status overlays.

## Verification

- `npm ci --ignore-scripts`: successful; dependency lock generated through npm.
- `npm test`: TypeScript passed; 186 Node tests passed, zero failures (18 session, 46 realtime, 122 beta).
- Selected Python suite: 184 passed, zero failures; includes mobile boot, chat, consultation request, security recovery/hardening, admin fixed-email OTP, account UI recovery, social API/comments/identity/native auth/safety/schema. There are 262 dependency/datetime deprecation warnings.
- New regressions cover image geometry/file constraints, duplicate-patient conflict identity, safe shared-media URL identity, real PDF/audio upload, spoof rejection and selected-case-media authorization. Existing tests for prior chat/request drafts now executed successfully.
- Android + iOS Expo/Hermes JavaScript exports succeeded after the changes.
- `expo prebuild --platform all --no-install` succeeded for both native projects; audio plugin did not add microphone permission. Generated native directories are verification output, not committed source. Warnings: store icon absent, expo-system-ui absent, Expo recommends RN 0.81.5 while existing pinned RN remains 0.81.4.
- A broader social-directory invocation stopped at collection: snapshot lacks `test_postgres`, and Playwright is not installed. Those PostgreSQL/browser tests were not counted as passing and were not deleted or weakened.
- No Android release APK, iOS IPA, emulator, physical-device, two-account live messaging, network-interruption or load-capacity acceptance performed. No 60,000-user capacity claim.

## Release blockers retained

Native signup/recovery parity, recording/microphone voice-exam integration, program/date picker, patient/tooth history and media parity, durable server message/media idempotency, full clinical concurrency handling, native account/profile parity and the remaining main-task modules still need work. Audio-file playback/upload is not microphone recording. OS PDF opening/sharing is not an embedded PDF editor. Annotation currently exports one edited image at a time.

Backend adapters in this branch are **not deployed**. The installed APK cannot gain these functions from a source commit alone. PR #257 remains draft; no main merge, live deployment or store publication.
