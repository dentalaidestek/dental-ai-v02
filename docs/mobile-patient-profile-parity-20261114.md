# Patient profile and tooth-chart adaptation — 14 November 2026

Continues PR #257 / issue #258. Initial comparison used `59912939d4f5481bfa3a808ccbd2ce9b3b9142af`; concurrent changes through `26b70657e5cc4695889198e840e1d72659e0bbd9` were merged and tested. No main merge, production deploy or store publication.

The patient and tooth-chart templates were also re-read from current `main`: they match the inspected templates apart from surrounding whitespace. The current main analysis-creation handler still enforces the four-image limit. This source comparison does not identify the exact commit deployed to production.

## Confirmed functional defects

1. The mobile patient profile presented additional explanatory sections instead of the web's real patient analysis history, and omitted portions of saved treatment records.
2. Patient/tooth history filters existed incompletely on the client, so reusing an unfiltered history list could show unrelated patient/tooth analyses. Both server authorization/filtering and client response identity checks now apply.
3. Native tooth status appearance substituted letters/symbols and fetched its base tooth atlas at runtime. This was not equivalent to the web's actual clinical overlays.
4. Two async mutation handlers — patient media upload and analysis creation — called the worker-thread-only `on_loop` bridge after committing the database transaction. A real TestClient upload reproduced `NoEventLoopError` after analysis/job persistence. They now await publication on the active ASGI event loop. The regression verifies successful media and analysis/job responses after persistence. This is a demonstrated defect, not proof that every APK loading problem has the same cause.

## Implemented patient flow

`NativePatientProfile` follows the web patient template's order: patient summary and quick actions, collapsed Patient Information, Clinical Images, Analysis History, Treatment History. The patient identity, complaint and saved fields come from the owned backend record. Placeholder disease/medication/allergy sections were not treated as clinical data.

| Web action | Native implementation |
|---|---|
| Patient summary / Uzmana Danış | Name, age, phone, patient number and complaint; patient context passed to existing expert/request flow |
| Expand patient information | Initially collapsed form; edit name/contact/TC/address/complaint; calendar birth-date field; existing two-stage deletion confirmation |
| Diş Şeması / AI Analiz | Existing native routes retain actual patient identity |
| Randevu | Patient-scoped form verifies the selected patient; calendar and hour/minute selection; appointment type and patient id submitted to the existing schedule validator; Turkey wall time matches the web conversion contract |
| Klinik Görseller | Photo/radiograph multi-selection and preview, explicit saving, per-file completion count, gallery pagination, native zoom, metadata and single/all deletion |
| Selected media → analysis | Server validates ownership and invokes the existing web analysis creator; returns a confirmed analysis id and opens the native result flow |
| Analiz Geçmişi | Patient-filtered paginated history, confirmed saved voice-review labels, protected asset/detail modal, clinical notes and native result opening |
| Tedavi Geçmişi | First three records with expand/collapse; material, result and doctor note; real create/edit and calendar dates |

Uploads and uncertain analysis/patient/treatment submissions do not automatically retry. Users check existing records before another attempt. The multi-image upload sends one file at a time through the existing endpoint; progress is completed-file count, not byte-level progress. This does not provide durable server idempotency.

The web gallery currently allows selecting 12 media records, while its analysis creation handler rejects more than 4. The native UI exposes the real server maximum of 4 before submission; production web code was not changed to conceal this inconsistency.

## Tooth chart

The atlas is now bundled in the app, with the same Git blob as the web asset: `8e4326bc172360a05ac06ee8147337240ff2a593`. Native SVG uses the web's caries/filling/crown gradients, status paths, root-canal lines, extraction cross and original implant SVG. Adult/primary FDI ordering and lower-jaw rotation remain. Native state/surface controls and save behavior remain functional; this is not a WebView.

The selected tooth's history now loads its actual analyses, including protected detail images, and treatment rendering includes the saved result and doctor note. Patient/treatment realtime events refresh the profile/chart; returning to a focused profile/history or foreground refreshes server data. Unsaved forms are not silently replaced by a realtime response. This is not conflict resolution for simultaneous clinical edits.

SVG blur/shadow/grayscale rendering and the surrounding layout are platform adaptations. No pixel-equality or physical-device appearance claim is made.

## Validation

- TypeScript passed; merged mobile suite: **204 tests passed, 0 failed** (18 session, 46 realtime, 140 beta).
- Selected Python suite: **187 passed, 0 failed**, including the three new patient parity/upload cases, existing boot/chat/request/security/admin/account/social tests. There are 274 deprecation warnings.
- New tests exercise actual profile expansion, account/patient switching while a request is pending, appointment payload identity/date/time, calendar leap years, patient/tooth filtering, status paths matching the web, selected-media ownership and post-persistence upload success.
- Source-location assertions for the old inline profile/navigation were migrated to the new component boundary, while retaining the same isolation requirements and adding renderer interaction tests. Concurrent schedule/API/credential-omission regressions remain in the suite.
- `npm ci --ignore-scripts`, Android/iOS native prebuild and Expo/Hermes exports succeeded. Prebuild still warns about the absent store icon, absent expo-system-ui and the existing RN 0.81.4 pin (Expo SDK 54 recommends 0.81.5).
- `react-native-svg` 15.12.1 matches Expo's `sdk-54/packages/expo/bundledNativeModules.json`. Native rendering is verified by TypeScript, path/geometry tests and bundle generation; there is no emulator/physical-device validation.

## Acceptance still open

This does not establish whole-app web parity. The remaining first-prompt work includes native account/signup/recovery/profile flows, full program calendar/editing, voice capture and full review acceptance, complete analysis result parity, messaging lifecycle/idempotency/device checks, other product modules and security/performance/release criteria. No authenticated production, two-account Android/iOS, bad-network, background upload, store build or 60,000-user capacity acceptance was performed.

Patient workflow still needs physical Android/iOS acceptance, durable upload/analysis receipts, protected clinical image metadata verification across every upload path, simultaneous-edit conflict behavior and pixel-level design review. In particular, the current direct analysis-image validation path has not been certified for EXIF removal; patient-gallery uploads use the existing sanitizer. General Program remains incomplete even though the patient → appointment form now has native date/time inputs.

These backend adapters are source-only until a separately authorized deployment. A source commit does not update an installed APK. CI status is recorded on PR #257 and issue #258 after pushing; local passing tests do not imply remote CI passed.
