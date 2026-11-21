# Native voice Bearer authentication and anamnesis parity — 2026-11-21

## Web-first trace

Reviewed the current web patient profile before touching native/backend code:

- `app/templates/patient_detail.html` renders only the seven explicitly approved voice-history fields, including systemic health history, medications and allergies. It labels the section as clinician-approved and warns that historical statements are not assumed to be current.
- The web history route is `GET /patients/{patient_id}/voice-exam/history`. `app/voice_exam.py` routes it through `_access()`, which uses `_user()`, then `main.get_current_user(request)` (the web cookie session).
- The native profile renders `NativePatientVoiceHistory`; `getVoiceHistory()` calls the same route with `Authorization: Bearer ...`. The native fetch intentionally omits cookies. The same `send()` helper is used by native extraction, final review and approval-related voice requests.

## Confirmed defect

The server-side voice authentication helper accepted only the web cookie session. It did not resolve the Bearer token sent by the native client. Consequently, the native approved-anamnesis request and the other native voice API calls could be rejected as unauthenticated even though the app had a valid mobile session. Existing client tests proved that a Bearer header was sent, but the backend route tests exercised only the mocked web-cookie path; they did not test the actual mobile authentication contract.

## Changes on the parity branch

- `app/voice_exam.py`: retained the existing non-GET same-origin / Fetch Metadata protection and cookie-session behavior, then added a Bearer fallback using the persisted `SessionToken` record. It checks expiry, active account, verified email and DOCTOR/ADMIN role. Expired tokens are revoked from the session table.
- Admin Bearer requests also require the existing allowlisted admin identity and `AdminVerifiedSession` marker. A plain mobile login token does not bypass the web admin second factor.
- Patient ownership still goes through `_owned()`; a different owner's patient remains indistinguishable as 404. The response retains `Cache-Control: private, no-store`, and the history payload continues to contain only completed `VOICE_REVIEW` jobs and explicitly saved fields. Transcript quotes remain empty.
- `mobile/src/voiceApi.ts`: explicitly sets `credentials: "omit"` so the native voice client relies on the verified Bearer path, not ambient cookies.

## Added regression coverage

Backend tests now exercise a cookie-free native Bearer session through an actual voice approval write and approved-history read; owner isolation; non-doctor and unverified users; expired and revoked tokens; admin second-factor enforcement; cross-site POST rejection; and private/no-store response headers. Native client tests assert both the Bearer header and cookie omission for voice POST/GET requests.

These tests were added to the existing suites; they were not weakened or rewritten to accept a changed production contract.

## CI evidence and limits

Immediately before these changes, the inspected CI runs on head `70379ae331393362bd07623acdf4fa813c2db383` completed successfully:

- Android run [#44932545236](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44932545236): TypeScript typecheck, session/auth tests, realtime/pagination tests, mobile beta regressions, Android/iOS Expo export, internal Android APK assembly and artifact upload all succeeded.
- Security recovery run [#44932545228](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44932545228): all native security jobs and the Python/PostgreSQL/web-security job succeeded.

Those runs predate the Bearer-auth changes and do not validate the new tests. The current branch head after this work is recorded in the PR; no matching new-head workflow run or commit status was available through the connected GitHub records at the time of this note. Therefore the new backend tests, native voice tests and Android typecheck are still awaiting execution on the new head. The earlier runner-allocation failures were pre-step infrastructure failures, not compiler/test diagnostics; their exact hosted-runner/account cause was not exposed by GitHub's records.

No main merge, live deploy, migration, APK publication or real patient-data mutation was performed.

## Additional route-mount defect found during final path verification

A second independent integration mismatch remained after fixing authentication: `mobile/src/voiceApi.ts` used the generic mobile API base `https://dentalai.tr/api/mobile/v1`, but `app/voice_exam.py` defines an unprefixed `APIRouter()` and `app/main.py` includes it without a prefix. Only `app/mobile_api.py` is mounted under `/api/mobile/v1`; neither the mobile analysis nor mobile modern router declares voice-exam aliases. The native voice client therefore targeted a path that was not registered by FastAPI.

Corrected the voice client's base to `https://dentalai.tr`, keeping the same authenticated root routes used by the web voice flow. Strengthened the native client regressions to assert the complete absolute POST and GET URLs, so a future reintroduction of the mobile prefix fails the test instead of passing a suffix-only assertion.
