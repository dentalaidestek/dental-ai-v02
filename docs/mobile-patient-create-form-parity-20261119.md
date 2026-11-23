# Native new-patient form parity — 2026-11-19

## Web-first inspection

Before the native change, the current branch's web references were read:

- `app/templates/patient_new.html`: the phone input is required, has `minlength=11`, `maxlength=11`, `pattern="05[0-9]{9}"`, numeric input mode and strips non-digits while typing.
- `app/main.py::create_patient`: the web handler independently validates a non-empty phone number but currently accepts an empty value if the browser constraint is bypassed.
- `app/mobile_api.py::mobile_create_patient`: the API also validates the Turkish prefix/length when a phone is supplied, but preserves optional phone for backward compatibility.
- `mobile/src/NativeNewPatient.tsx`: the native form previously labelled phone as optional-looking and allowed submission with an empty phone. Its input stripped non-digits and capped at 11 characters, but it did not apply the web form's required-field rule or prefix check before the request.

## Gap and change

The visible web contract requires a Turkish mobile number, while the native create form could create a record without one. This was a form-parity gap, not an API authorization issue.

- Added `patientCreateValidation.ts` as a pure native form validator.
- Phone input normalization now shares the web behavior: digits only, at most 11 characters.
- Native submission now blocks an empty phone and rejects anything other than `05` followed by nine digits before calling the API.
- The field is labelled `Telefon *`, retains the 11-character limit and phone keyboard, and opts into the platform telephone autofill.
- Existing duplicate-patient confirmation and uncertain-response behavior are unchanged.
- Backend API phone optionality is intentionally retained for older installed clients; the native form enforces the current web UI contract without silently breaking older clients.

## Regression coverage

- `mobile/tests/patientCreateValidation.cjs`: required phone, valid Turkish number, invalid prefix/length, name validation and numeric input normalization.
- `mobile/tests/patientCreate.cjs`: native renderer checks that an empty phone makes zero API calls and that a valid formatted phone is normalized before submission.
- Both tests are registered in `npm run test:beta`.

## Validation boundary

The source and test files are committed on `feature/mobile-web-parity-20261110`. This connector runtime cannot execute the repository's Node/React Native test suite or TypeScript compiler. The helper logic will be independently smoke-checked here, but that is not a substitute for `npm run typecheck` or `npm run test:beta`. Current-head GitHub Actions status is checked separately; no green CI is assumed.

No backend behavior, patient record, database schema, main branch, production deployment or store build was changed.
