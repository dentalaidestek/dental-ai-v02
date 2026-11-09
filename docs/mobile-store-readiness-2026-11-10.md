# Mobile release gates — 10 November 2026

This is an internal beta, not a store-ready or clinically validated release.

## Build and signing

- Android application ID: `tr.dentalai.app`; beta version `0.2.0` / code `2`.
- iOS bundle ID: `tr.dentalai.app`; build `2`. Availability of the identifiers in the developer accounts has not been checked.
- `eas build --platform android --profile preview`: internal APK; `--profile production`: store AAB. Requires the owner's Expo/EAS project association and signing setup; do not invent `extra.eas.projectId`.
- `eas build --platform ios --profile simulator`: simulator; `--profile production`: device/TestFlight preparation. Apple Developer membership, App Store Connect access, provisioning and signing are not present/verified in this session. Linux Metro export does not compile an IPA.
- Local `expo prebuild --platform android` plus Gradle `assembleRelease -PreactNativeArchitectures=arm64-v8a` embeds the JS bundle. The generated development key is for internal testing only. Never upload that artifact to Google Play as a production signing setup.
- CI retains internal APK artifacts for 14 days. No store submission, EAS paid build, production deploy or main merge is performed.
- No OTA updater was added. Recovery is a source revert followed by a build with an increased platform build number, staged internal testing, then store rollout; backend changes must remain compatible with installed clients.

## Privacy and permissions

Camera/gallery are requested when chosen. Image-picker microphone permission is disabled until a native voice feature is actually implemented. Android backup is disabled; tokens and social drafts use SecureStore. Photos are not written to analytics. PostHog replay and automatic content capture are not enabled.

Release blockers: native account/data deletion and consent/notice review, full ownership tests for every endpoint (only selected social/native paths exercised here), lost-device/revocation UX, push delivery/permission flows, data retention/backup erasure policy, custom final icon/splash, privacy-policy and store data-safety declarations, physical-device tests and crash monitoring. Chat sends the existing consultation message contract; unused crypto helpers do not establish E2EE or multi-device key recovery. `usesNonExemptEncryption` is conservatively true pending the actual cryptography/export review, not an E2EE claim.

## Health software assessment

Dental image interpretation and treatment decision support need an intended-use and medical-device qualification/classification assessment. A disclaimer alone does not resolve the classification. No definitive device class or regulatory clearance is claimed here. Document the target countries, intended users, input images, outputs, role of the clinician, contraindications/limitations, validation population and harms from a wrong result before public clinical distribution. TİTCK publishes software qualification/classification and clinical evaluation guidance; obtain a competent regulatory assessment before deciding conformity/registration obligations.

Patient health data and cloud/provider transfers require a documented lawful basis, notices, appropriate safeguards and a transfer assessment. Explicit consent is not a universal substitute for all processing/transfer requirements. The real Render/Modal/storage/AI provider countries, subprocessors, retention and contracts have not been verified in this task.

## Official references checked

- Expo SDK 54 / React Native 0.81: https://expo.dev/changelog/sdk-54
- Apple review medical accuracy and privacy requirements: https://developer.apple.com/app-store/review/guidelines/ (1.4.1, 5.1)
- Apple in-app account deletion: https://developer.apple.com/support/offering-account-deletion-in-your-app/
- Google Play health content/services: https://support.google.com/googleplay/android-developer/answer/16679511
- TİTCK software/device guidance and regulations: https://www.titck.gov.tr/faaliyetalanlari/tibbicihaz/tibbi-cihaz-mevzuati
- KVKK international transfers: https://www.kvkk.gov.tr/Icerik/2053/Yurtdisina-Aktarim
- PostHog privacy controls: https://posthog.com/docs/session-replay/privacy

## Device acceptance matrix (all NOT RUN on physical hardware)

Android and iOS separately: login/email code; token expiry/revocation; new/search/page patient; image permission denial/camera/gallery/upload and job resume; result history and confidence threshold; published/pending/rejected post; photo/link; post edit retains likes/comments; pin mark; comment/reply/like/follow/report; draft survives close/restart and ambiguous response; consultation/messages; notification target; keyboard and back; airplane mode; force-close; background/foreground. Academic document/index/quiz and native voice tests remain phase two because those screens are not implemented.
