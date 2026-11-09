# Dental AI Android / iOS native beta

React Native + Expo + TypeScript; no WebView. Uses the existing mobile API,
session records, patient data, analysis jobs and social/moderation tables.
AI providers and model routing are unchanged.

## Develop and verify

```sh
cd mobile
npm ci
npm test
npx expo start
npx expo export --platform android --platform ios
```

Tabs: Ana Sayfa, Dental Akış, AI Analiz, Hastalar, Profil. Program, academic
questions, consultation/messages and notifications remain available through the
home/profile stacks. Native voice and academic document upload are not implemented.

## Internal Android APK

```sh
npx expo prebuild --platform android --no-install
cd android
./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a --no-daemon --max-workers=2
```

This embeds JS and uses the generated development signing key, for internal
testing only. CI uploads the APK as `dental-ai-beta-arm64`. It targets ARM64
phones; do not distribute it as a production store-signed app.

The new native Dental Akış authorization and expert-photo endpoint require
the backend changes in the same PR. Until the backend is approved and deployed,
the existing production social API rejects the app's Bearer requests. Main and
production were not changed by this work.

## EAS and stores

```sh
eas build --platform android --profile preview
eas build --platform android --profile production
eas build --platform ios --profile simulator
eas build --platform ios --profile production
```

EAS project association and store signing credentials must come from the owner's
accounts. No invented project UUID or credential is checked in. iOS Metro export
does not produce a signed IPA or prove TestFlight/device compatibility.

See [audit](../docs/mobile-beta-2026-11-10.md) and
[release gates](../docs/mobile-store-readiness-2026-11-10.md) for tested scope,
deferred features, device acceptance and health/privacy obligations.
