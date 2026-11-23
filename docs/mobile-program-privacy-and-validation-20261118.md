# Mobile Program appointment validation and privacy — 2026-11-18

## Web flow reviewed first

Re-read `app/templates/program.html`, `app/templates/program_form.html`, the shared `_validate_schedule_input` helper, and the native `NativeProgramEditor` / `programApi` flow on `feature/mobile-web-parity-20261110`.

## Findings and changes

1. The web form declares a 160-character location and 2,000-character notes limit, but the shared server validator previously trusted browser maxlength. A crafted web form request could bypass the location limit; the mobile Pydantic model also allowed 1,000 characters. The shared validator now enforces 160/2,000 on both web and native requests, and the mobile request model rejects an overlong location before route execution.
2. The native conflict-advice endpoint returned up to ten event titles although the editor only displayed the total count. Titles can contain patient-identifying text and were not needed by the UI. The response is now the minimal `{advisory, total}` shape.
3. The web Program form does not require a separate conflict-advice endpoint to save. Native previously failed the entire save when this additional advisory request had a transient network/5xx error. Native now offers an explicit confirmation to continue without the advisory check only for network/408/429/5xx failures. Cancel remains the default. Authentication and validation failures (401/403/422 and other non-transient statuses) still block submission.

## Regression coverage

- Python shared-validator checks for 161-character location and 2,001-character notes.
- Mobile API request validation for overlong location and notes.
- Conflict endpoint response shape asserts that event titles/items are not returned.
- Native component tests cover explicit opt-in after a transient advisory outage and fail-closed behavior for 401.

## Validation boundary

The GitHub Actions workflows are currently manual-only (`workflow_dispatch`) on this branch, so no workflow run is associated with the latest commit. This preserves the previously requested pause on automatic CI/email triggers. The full Node/TypeScript/pytest/Gradle checks remain unexecuted in this connector-only run; these committed tests are not represented as passing.

No main merge, production deploy, migration, APK publication, or patient-data mutation.
