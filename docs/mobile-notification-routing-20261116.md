# Native notification target parity — 2026-11-16

## Web flow inspected first

Reviewed:
- app/templates/base.html notification center rendering and anchor behavior;
- app/main.py _notify_user target validation and the actual target_url values emitted by the web workflows;
- app/mobile_api.py mobile notification payload and read endpoint;
- mobile/src/ModernScreens.tsx native notification center;
- mobile/App.tsx registered native stack routes.

The web notification center renders an anchor when a notice has a target URL. The canonical backend targets observed on this branch include /expert-support/cases/{id}, /expert-support/profile, /expert-support, /program, and /support-request.

## Reproduced native parity defect

The old native resolver recognized /consultations/{id}, /expert/consultations/{id}, /cases/{id}, /consultations, and /patients/{id} only. The actual web-generated /expert-support/cases/{id} route therefore did not open the corresponding native consultation chat. Program reminders and expert-directory/profile notices also remained in the notification center without navigating.

A second behavioral defect was that native marked a notice read before deciding whether its target could be opened. An unsupported target was therefore silently consumed even though no corresponding native screen existed.

## Changes

- Added mobile/src/notificationTarget.ts as a pure, typed resolver for only known same-origin web paths.
- Mapped /expert-support/cases/{id} to ConsultationChat with the same case ID used by the canonical mobile chat API.
- Mapped /expert-support to ExpertDirectory.
- Mapped /expert-support/profile to ExpertManagement.
- Mapped /program to Program.
- Preserved nested patient navigation for /patients/{id} and legacy consultation aliases.
- Rejects external, protocol-relative, backslash/control-character, malformed and unsafe numeric targets. No URL is opened in a browser and no target value is treated as an authorization credential.
- The native center now resolves a target before changing read state. An unsupported path such as /support-request shows a clear message and remains unread rather than pretending it opened.
- For supported routes, the native screen still navigates if the read-marker request fails, matching the web anchor's behavior; the notice remains unread on the server and can be reconciled when the user returns.
- Added the new regression file to npm run test:beta.

## Verification boundary

The isolated Node regression suite passed 10/10 against the resolver and a source-contract fixture. The committed test file additionally reads the actual ModernScreens.tsx at repository test time. The module's standalone TypeScript check is separate from the full Expo application typecheck.

The current GitHub Android and security jobs have runner_id=0, empty runner names, and zero steps. Re-running the latest failed jobs was accepted, but Android typecheck/APK and both security jobs again failed without starting a runner; no npm ci, tsc, Gradle or pytest step ran. This does not establish a source-code test failure or a green CI result. The repository owner still needs to inspect hosted-runner availability, account billing/usage and Actions service access.

The /support-request path still has no native support-ticket screen in this branch. It is intentionally reported as unsupported and left unread; no unrelated screen is opened as a substitute. Native Expo push token registration, OS delivery, tap/deep-link behavior from a killed app, duplicate delivery and physical-device acceptance remain separate release gates.

No backend target, notice payload, patient data, provider, schema or production setting was changed. No main merge, production deploy, APK/IPA publication or patient-record mutation was performed.
