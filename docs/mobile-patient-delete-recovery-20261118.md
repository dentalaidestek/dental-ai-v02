# Native patient deletion recovery — 2026-11-18

## Web flow inspected first

The web patient detail page (app/templates/patient_detail.html) keeps patient editing and deletion inside the **Hasta Bilgileri** disclosure. Deletion requires a separate confirmation modal and posts to the web deletion route. The mobile adapter is intentionally stricter: it refuses to delete a patient while any analysis, treatment, tooth status/surface, clinical media, schedule event, or consultation case remains. Full clinical erasure still requires a separate audited workflow.

## Gap found

The native profile previously sent DELETE /api/mobile/v1/patients/{id} without an idempotency key. If the server committed the deletion but the response was lost, the app retained a stale profile and a retry received 404. Unlike media deletion, the patient endpoint had no durable replay receipt. The local UI also had no durable intent to restore after an app restart.

## Change

- Native deletion creates a random request key and persists a versioned intent in the account-and-patient-scoped SecureStore key dai.patient-delete.v1.<user>.<patient>.
- No DELETE request is sent unless the intent is durably stored.
- An uncertain response keeps the exact same key. The clinician must explicitly confirm **Bekleyen Silme İşlemini Doğrula**; a new key is never generated for recovery.
- The mobile API validates the key, patient ID, and already_deleted receipt field.
- The backend binds the hashed request key to the authenticated owner and patient ID. It stores only a SHA-256 source fingerprint and empty payload in the existing WorkJob receipt table; no name, complaint, media, or clinical content is copied into the receipt.
- The receipt and patient deletion commit in the same database transaction. An account-row lock serializes same-owner deletes; the unique WorkJob dedupe key is the cross-process constraint.
- A replay returns already_deleted=true only when the receipt matches and the patient row is still absent. Reusing the same key for another patient, or finding a restored row, returns 409.
- The existing dependent-clinical-record guard remains unchanged. A 409 does not create a receipt and does not erase any clinical history.
- The existing work-history pruning bounds delete tombstones to 30 days. After expiry, a missing patient returns 404; the native profile treats that as an inaccessible/missing route and returns to the patient list.
- Corrupt, empty, wrong-account, or wrong-patient local intents fail closed. Profile edits, treatment writes, and quick actions stay blocked until the intent state is known and settled.

## Regression coverage added

Python (tests/test_mobile_patient_parity.py):
- response-loss replay returns the same successful deletion without a second receipt;
- key reuse for a different patient returns 409;
- another account cannot replay the receipt;
- clinical dependencies block deletion without creating a receipt;
- a restored patient row is not falsely reported as deleted;
- tombstones are pruned by the existing 30-day history policy;
- malformed keys do not mutate the patient.

Native (mobile/tests/patientProfileUI.cjs and mobile/tests/patientParity.cjs):
- request key is stored before DELETE;
- ambiguous response preserves the exact key and recovery reuses it;
- corrupt/empty intent blocks destructive actions;
- SecureStore write failure prevents network deletion;
- 404 exits the stale patient route;
- API validates the request key and receipt response.

Commands to run when a runner is available:

\`\`\`bash
pytest -q tests/test_mobile_patient_parity.py
cd mobile
node --test tests/patientProfileUI.cjs tests/patientParity.cjs
npm run typecheck
\`\`\`

## Verification boundary

The changes are committed to feature/mobile-web-parity-20261110. The repository's latest GitHub Actions runs on the previous head failed before steps were allocated (steps=[], runner ID 0, missing job-log blob). The new tests are committed but are not reported as executed or passing in this environment. Staging PostgreSQL concurrency and Android device acceptance remain open.

No main merge, production migration, live deploy, APK/IPA publication, or real patient-data mutation was performed.
