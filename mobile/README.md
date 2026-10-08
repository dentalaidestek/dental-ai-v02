# DENTAL AI Android

Native React Native / Expo client for the existing Dental AI backend.

- Backend remains FastAPI/PostgreSQL/R2/Gemini.
- Android uses JSON APIs under /api/mobile/v1.
- Authentication reuses the existing session-token system.
- Session token is stored with Expo SecureStore.
- The app is intentionally separate from the production web UI.

## Local development

    cd mobile
    npm install
    npx expo start

## Android APK

The preview EAS profile is configured for an installable APK:

    eas build --platform android --profile preview

Production Play Store artifact:

    eas build --platform android --profile production

No production deployment or main-branch merge is performed by this branch.

Native workspace: realtime, notifications, consultation, Academic AI, analysis history and patient media are wired on the current branch.
Verification retry after native API syntax repair.
