# Native patient profile account-switch mutation audit — 2026-11-14

## Web/mobile functional rule
A patient edit belongs only to the authorized patient and account that initiated it. Switching to another patient must not inherit a pending edit lock, form state, or a late error from the previous patient. This preserves web patient-scoped edit semantics in the native profile.

## Confirmed source defect
Before commit 94fae52f, `NativePatientProfile.savePatient` set `lock.current=true`. Its `finally` reset the lock only if `current()` remained true. When the token or patient ID changed during the request, `current()` became false; the old request could never unlock the ref. The component's scope-reset effect cleared forms but did not clear `lock.current` or `busy`. Subsequent edits for the new patient silently returned early.

## Changes
- Clear the mutation lock and busy indicator on scope change.
- Reset the previous patient's treatment editing ID and expanded treatment state.
- Add a regression exercising a pending edit for account A, a switch to B, a successful B edit and a delayed A failure. The delayed error must not appear in B's profile.

## Verification limits
These are committed source changes, not a physical-device acceptance result. The regression and full mobile TypeScript suite have not been executed in this connector-only run.

The inspected current PR head before these changes was `10d4dec5c2c388bbacfdbef14f59ad69e09c2fa4`; the associated Android run `43611394271` failed both typecheck and beta-apk. The job API exposed `steps:null` and `logs_url:null`; the security workflow `43611394162` also failed with unavailable steps. This is insufficient evidence to attribute CI failure to a TypeScript or application security defect.

## Next
Run `cd mobile && npm ci && npm run typecheck && node --test tests/patientProfileUI.cjs` in a runnable checkout, inspect failed assertions, and test a delayed patient edit while switching accounts on an Android device. Obtain actionable CI runner logs before claiming a remote root cause. No main merge or production deployment.
