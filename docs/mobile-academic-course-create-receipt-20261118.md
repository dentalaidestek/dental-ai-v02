# Native Academic course-create idempotency — 2026-11-18

## Web-first contract

Re-read `app/templates/notes_course.html`, `app/templates/notes_ai.html`, and the canonical `create_study_course` handler in `app/main.py`. The web form remains a normal form post. The additive native adapter uses the same `StudyCourse` model and owner scope but adds a durable receipt because a mobile request can commit while its response is lost.

## Receipt contract

- Key scope: `(owner_user_id, request_key)`, enforced by a database unique constraint.
- Request keys are 16–80 ASCII letters, digits, underscore or hyphen; the native client creates a UUID before POST.
- Payload fingerprint: SHA-256 over versioned, normalized title and description. The receipt stores no title, description, token or clinical content.
- Same owner/key + same fingerprint returns the original course.
- Same owner/key + different fingerprint returns HTTP 409.
- Receipt lookup is owner-scoped; an unknown key, including a key owned by another account, returns `workspace: null`.
- A receipt whose course was subsequently deleted returns HTTP 410. The old key never recreates a course.
- Course and receipt commit in one database transaction. PostgreSQL serializes same-owner create attempts with a transaction advisory lock; the unique constraint remains the final race guard.
- Receipts deliberately have no course foreign key so they survive course deletion and prevent delayed retries from recreating deleted content.

## Native recovery

Version-2 SecureStore intents persist the request key, exact title and description before POST. On app restart or after a lost response, the app checks the server receipt first. If no receipt exists, the user can retry the exact payload with the same key; the server still provides the atomic duplicate guard. Legacy version-1 intents remain read-only and use their prior list-reconciliation behavior; they are never converted into a new request key.

## Migration

Schema revision 17 creates `studycoursecreatereceipt` under an advisory transaction lock from revision 16. The migration verifies the unique owner/key constraint before advancing the revision. Fresh databases receive the model through `SQLModel.metadata.create_all`. This migration is code only; it has not been run against production.

## Regression coverage

- Same-key/same-payload replay returns one course.
- Same-key/different-payload returns 409.
- Another account cannot read or replay the first account's receipt.
- A deleted course returns 410 for its old key.
- Invalid keys are rejected.
- Native intent persists a stable key and retries the exact payload.
- A committed request with a lost response is recovered from GET receipt without a second POST.

The Python and Node regression tests are committed but require an allocated runner or local dependency environment to execute. No PostgreSQL concurrency test, production migration, main merge or live deploy is claimed.
