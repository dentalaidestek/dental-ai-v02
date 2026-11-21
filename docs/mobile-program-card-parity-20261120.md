# Native Program card parity — 2026-11-20

## Web-first flow inspected

Before editing native code, the current branch versions of these files were read:

- `app/templates/program.html`
- `app/templates/program_form.html`
- `app/mobile_program_api.py`
- `mobile/src/NativeProgram.tsx`
- `mobile/src/NativeProgramEditor.tsx`
- `mobile/src/programApi.ts`

The web Program card renders the event type as a distinct label, shows a `Bugün` marker on today's date group, exposes recurring/completed state, and links a patient name to `/patients/{patient.id}`.

The native card previously rendered the patient name as plain text and placed event type, recurrence and completion in one muted sentence. A clinician could not open the linked patient from the appointment card, even though the API already returned the owned `patient_id`.

## Changes

- Native Program now uses the root stack to navigate from an owned appointment patient to the nested `Patients → PatientDetail` screen.
- The patient action is rendered only when both the display name and a positive safe-integer patient ID are present. Events without a linked patient remain unchanged.
- Event types now use the existing Program type color map as a compact label, matching the web card's information hierarchy.
- Weekly recurrence and completion state are separate, readable chips.
- Today's date group receives the same `Bugün` marker as the web view.
- No patient data is copied into local storage or analytics; navigation passes only the already-authorized patient ID through the native route.

## Regression coverage

`mobile/tests/programParity.cjs` adds component-level checks for:

1. Opening the exact patient profile from a Program card.
2. Showing the event type, recurring state, completed state and today marker.

The existing Security Recovery `native-program-security` job already runs `programParity.cjs`; the Android beta suite runs it through `test:beta`.

## Validation boundary

The change is committed, but the latest Android and Security Recovery runs must finish before this UI change is considered CI-verified. A connector-only isolated source review is not a substitute for the full React renderer test, TypeScript project check or Android build.

No backend API, patient ownership rule, database schema, migration, reminder queue, main branch or production deployment was changed.
