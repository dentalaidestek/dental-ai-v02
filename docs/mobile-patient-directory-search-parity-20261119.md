# Native patient directory search parity — 2026-11-19

## Web-first inspection

Read the current branch's:

- `app/templates/patients_all.html`: in-page search filters the rendered directory by first name, last name, anonymous patient number and phone. The web row displays both patient number and phone.
- `app/templates/patient_search.html`: the separate server-backed search accepts TCKN, first name, last name and patient number, displays at most 50 matches, and orders by surname/name.
- `app/main.py::all_patients` and `app/main.py::search_patients`: normal users are scoped to their own patient records; the web ADMIN role has broader directory visibility.
- `app/mobile_api.py::mobile_patients`: native uses bounded 30-row offset pages and owner-only scope. Before this change it searched name, phone and anonymous ID but omitted TCKN, returned newest-first even for search, and did not set the shared private/no-store response headers.
- `mobile/App.tsx::Patients` and `PatientRow`: native already used server pagination and a search submit action, but displayed either phone or patient number (not both), did not advertise TCKN search, and required a manual footer action for every next page.

## Changes

- Added TCKN to the mobile directory's server-side search predicate. TCKN remains search-only: `_patient_payload` still does not return it in list rows.
- Applied the existing `_mobile_private_no_store` policy to the patient list response: `Cache-Control: private, no-store`, `Pragma: no-cache`, and `Vary: Authorization`.
- Kept strict `Patient.owner_user_id == user.id` scoping for the native list and detail path. Search does not reveal another account's patient existence.
- Reused one filter set for page and count queries and changed the count to `count(Patient.id)`, avoiding the previous full-row subquery.
- Search results now use the web's surname/name ordering with an ID tie-breaker for deterministic offset pages; an unfiltered directory remains newest-first.
- Added a small native presentation helper for web-aligned whitespace normalization, separate patient-number/phone labels, and an age label that correctly renders age zero.
- Native search is capped at the server's 100-character contract, supports the web search fields in its placeholder, shows an explicit no-match state, and automatically requests the next bounded page near the end of the list. The accessible “Daha fazla hasta” control remains as a fallback.
- The API client normalizes whitespace before URL encoding and continues to omit ambient cookies, sending only the explicit bearer token.

## Regression coverage added

- `tests/test_mobile_patient_parity.py`: web/native TCKN search parity, partial TCKN matching, owner isolation in both directions, no-store/Vary headers, no TCKN in list payload, and alphabetical search ordering.
- `mobile/tests/patientDirectoryPresentation.cjs`: Turkish whitespace normalization, both directory labels, age zero, bearer-only normalized API query and native source wiring.
- Registered the new native regression in `npm run test:beta`. The existing Security Recovery pytest command already includes `tests/test_mobile_patient_parity.py`; no workflow expansion was needed.

## Validation boundary

The source and test files were committed and read back from GitHub. The new pytest and Node tests were not executed in this connector-only run. Full `npm run typecheck`, `npm run test:beta`, Python Security Recovery, Expo export, Android Gradle/APK, physical-device and 60,000-user load acceptance remain open.

At the starting HEAD `a156fc7`, PR workflow-run lookup and combined status were empty. The Android and Security Recovery workflows are deliberately `workflow_dispatch`-only while the previous push-triggered runs fail before their first step. A historical Android job had an empty step list and its log download returned `BlobNotFound 404`; TypeScript, Gradle and pytest therefore have not produced a source-level failure to fix. No workflow was dispatched in this run, to avoid restarting the previously noisy CI notification path. The exact hosted-runner/account/billing cause is not exposed by the available GitHub records.

The web ADMIN directory's broader cross-owner visibility is not copied into native: native patient detail remains owner-only, so widening only the list would expose rows that the mobile profile route cannot safely open. That role-policy parity needs a separate, explicit permission review rather than an accidental list-only expansion.

No patient record, database schema, migration, main branch, production deployment or store build was changed.
