# Patient directory live-search parity — 2026-11-20

## Web-first inspection

Reviewed before changing native code:
- `app/templates/patients_all.html`: the directory search input listens to the `input` event and filters rows immediately.
- The row's searchable fields are first name, last name, anonymous patient number and phone. The web directory keeps the search local to the rendered directory; it does not issue a request per keystroke.
- `app/templates/patient_detail.html`: profile quick actions include expert consultation, FDI tooth chart, AI analysis, appointment and treatment. The profile edit form includes name, phone, TCKN, birth date, address and chief complaint; deletion uses a second confirmation.
- `app/main.py`: HTML directory is authenticated; non-admin list results are scoped to `owner_user_id`. Patient detail independently checks ownership before loading analyses, treatments and profile data.

## Native comparison

The native directory already uses authenticated, bounded server-side pagination (30 records/page), a 100-character query bound, empty/error states, pull-to-refresh and patient realtime refresh. It deliberately does not download the full patient register to filter locally. The native profile already has optimistic-revision editing, conflict resolution, a durable/idempotent delete intent, treatment paging, clinical media, analysis history and separately loaded clinician-approved voice anamnesis.

One concrete UX parity gap remained: native search was only applied by the keyboard submit or Ara button, while the web directory reacts as the user types.

## Change

- Added `PATIENT_DIRECTORY_SEARCH_DEBOUNCE_MS = 300` to the directory presentation module.
- Added a cancellable 300 ms effect in the native patient directory. It sends bounded server-side paged search after typing pauses, while the existing Ara/keyboard action remains immediate.
- No local full-register caching, polling, additional patient fields, or PII display was introduced.
- Added `patientDirectoryLiveSearch.cjs` and registered it in `npm run test:beta`.

## Privacy and correctness

- Search requests continue through the existing bearer-authenticated API client with `credentials: omit`.
- TCKN is not added to patient list rows.
- Patient owner scoping remains a backend responsibility; no broadening of access or route changes were made.
- Existing profile edit revision checks and delete intent/idempotency behavior are unchanged.
- No clinical record or production data was accessed or mutated.

## Validation status

The regression test was added to the beta suite but could not be executed from the GitHub connector environment. The new commit has no associated workflow runs and the combined commit status list is empty. Therefore no test pass or green CI is claimed. Android full typecheck, Gradle build, security pytest and physical-device acceptance remain outstanding.

No main merge, production deploy, migration, APK publication or IPA publication.
