# Native appointment patient selector parity — 2026-11-19

## Web-first inspection

Reviewed the current branch before changing native code:

- `app/templates/program_form.html`: the web Program form exposes an optional patient selector and retains the selected patient ID when editing or opening a patient-linked appointment.
- `app/templates/program.html`: appointment cards link back to the associated patient profile.
- `app/main.py` program validation: the shared `_validate_schedule_input` path resolves a selected patient through the current user's ownership boundary.
- `app/mobile_program_api.py`: the mobile program adapter serializes only the owned patient ID/name for calendar events.
- `app/mobile_api.py::mobile_patients`: the native picker can use the existing bounded, owner-scoped search endpoint. It searches name, phone, anonymous patient number and TCKN; the list payload intentionally omits TCKN.
- `mobile/src/NativeProgramEditor.tsx` and `NativePatientSelect.tsx`: the custom native picker was already paginated, but its field did not cap input at the API's 100-character limit and its placeholder advertised only name/patient number. Result rows omitted phone, making same-name patients harder to distinguish.

## Changes

- Added `patientSelectPresentation.ts` to normalize Turkish/Unicode whitespace consistently with the patient directory, enforce the 100-character query contract, centralize empty/loading/error copy, and reuse the directory's safe patient-number/phone labels.
- Updated the native appointment picker to advertise the actual supported search fields: name, surname, patient number, phone and TCKN.
- Added `maxLength=100`, explicit search-key submission, debounced normalized search and a clear-search action.
- Result rows now show patient number and phone to disambiguate same-name patients. TCKN remains search-only and is not rendered or added to accessibility labels.
- Improved the modal hierarchy, patient initials, row affordance, loading/empty/error states, retry action, keyboard tap behavior and automatic bounded pagination; retained the accessible “Daha fazla hasta” fallback.
- Added `patientSelectParity.cjs` and registered it in `npm run test:beta`.

## Privacy and compatibility

No backend route, patient record, database schema, migration, authorization policy, appointment mutation or reminder behavior changed. Search still uses the existing bearer-only API request, owner-scoped query, private/no-store response, and a maximum of 30 records per page. The UI never renders TCKN; it is used only by the server search predicate.

## Validation boundary

The new regression covers Turkish whitespace normalization, the 100-character bound, safe row details, explicit empty/loading/error copy, search-field accessibility text, pagination and absence of direct TCKN rendering. The test is committed but the repository's Node/React Native suite and TypeScript compiler could not be executed in this connector-only run. GitHub Actions currently has no run for the new HEAD; historical push-triggered Android jobs failed before any step with empty step arrays. No CI pass, Android build or physical-device acceptance is claimed.

No main merge, production deploy, APK/IPA publication or clinical record mutation.


## Follow-up regression

A source review of the new pagination footer found that a failed next-page request could show both the retry action and the normal “Daha fazla hasta” action. The normal action is now hidden while a page error is present; the retained cursor is retried only through the explicit retry control. The native regression asserts this state. Commits: `ffe4b3f` and `ecebb85`. The isolated 4-test suite was rerun after this fix and passed.
