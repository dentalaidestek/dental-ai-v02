# Program cache privacy and calendar grouping — 2026-11-19

## Web-first review

Before changing native or API code, re-read:

- `app/templates/program.html`: today/week/month views, period navigation, event grouping by day, event actions and copy sheet.
- `app/mobile_program_api.py`: native calendar, event recovery, mutation receipt and conflict-advice responses.
- `app/mobile_api.py::_mobile_private_no_store`: the shared response policy already used by participant-scoped clinical endpoints.
- `mobile/src/NativeProgram.tsx`, `programApi.ts` and `tests/test_mobile_program_parity.py`.

## Newly confirmed privacy gap

The native Program API returned patient names, appointment titles, locations, notes and event state from these routes without consistently setting the shared private response headers:

- `GET /program`
- `GET /program/mutations/{request_key}`
- `GET /program/events/{event_id}`
- `POST /program/conflicts`
- Create, edit, copy, complete and delete acknowledgements.

Although every query already enforces the authenticated owner boundary, the absence of an explicit cache policy left account-scoped calendar data with weaker HTTP cache protection than the patient and clinical-media APIs.

## Changes

- Reused `_mobile_private_no_store` for all nine Program route response shapes.
- Responses now carry `Cache-Control: private, no-store`, `Pragma: no-cache` and `Vary: Authorization`.
- The same injected response object is used when create/edit routes reuse the owned event serializer, so those acknowledgements do not lose the headers.
- No event fields, owner checks, request receipts, recurrence logic, reminder scheduling or patient data were changed.

A separate native/web presentation gap was also confirmed: the web groups weekly occurrences under a heading for each date, but native rendered a flat list containing only the time. On a week with multiple days, an event card did not state which day it belonged to.

- Native Program now emits one accessible date heading at each date boundary.
- The boundary check uses the complete ordered FlatList data, so appending a later cursor page does not repeat the heading when the next page continues the same day.
- Month markers, day selection, pagination, copy-day filtering and mutation controls are unchanged.

## Regression coverage

- `tests/test_mobile_program_parity.py` checks cache headers on calendar reads, conflict advice, create/edit acknowledgements, event detail, mutation receipt, copy, complete and delete.
- `mobile/tests/programParity.cjs` verifies that multiple same-day events share one heading and the next day gets a new heading.
- The Python test module is already included by the Security Recovery workflow; the native test is already part of `npm run test:beta`.

## Validation boundary

GitHub source inspection confirms the changed routes call the shared cache helper and the new tests are present. The full Python integration test, React renderer test, `npm run typecheck`, `npm run test:beta`, Expo export and Android build were not run in this connector-only environment. A local checkout attempt could not resolve `github.com`; the tests are committed, not claimed as passing.

The latest branch head has no associated workflow run or combined status. Earlier Android typecheck and Security Recovery jobs had no executed steps and their log blobs returned 404, so those failures do not identify a TypeScript or pytest source failure. Hosted-runner/account/billing sub-cause remains unexposed.

No migration, main merge, production deploy, APK/IPA publication or patient-record mutation was performed.
