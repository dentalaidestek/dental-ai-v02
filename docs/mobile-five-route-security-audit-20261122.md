# Mobile five-route security and contract audit — 2026-11-22

Scope: PR #257, branch `feature/mobile-web-parity-20261110`. No production data, credentials, or clinical media were used.

## Web-first contract checked

- Patient clinical media upload is owned by the authenticated patient owner; the web media handlers in `app/main.py` check patient ownership before returning or mutating media.
- Analysis access is resolved through the shared analysis ownership helper in `app/mobile_analysis_api.py`; receipt lookup also verifies patient ownership and the analysis-to-patient relationship.
- Expert chat attachments reuse the web handlers `expert_support_media_message` and `expert_support_message_media`. Those handlers re-check case participation, blocked-user state, case lifecycle, retention/deletion, and message ownership under the case lock.
- Text message receipt lookup is case-participant scoped and sender scoped. The receipt stores a compact reference/hash, not message content.

## Native endpoints and expected invariants

| Native endpoint | Contract / regression coverage |
|---|---|
| `GET /api/mobile/v1/analyses/uploads/receipt` | Patient owner + analysis relationship; no-store; same key returns same analysis/job; changed payload conflicts; missing receipt is distinct; lost post-commit response can be recovered. |
| `GET /api/mobile/v1/patients/{patient_id}/media/uploads/{request_key}` | Patient owner + receipt owner/resource scope; keyed fingerprint; no storage path/fingerprint leakage; same key replay; changed bytes conflict; deleted media is not resurrected. |
| `GET /api/mobile/v1/consultations/{case_id}/message-receipt` | Case participant and original sender scope; private no-store + Vary Authorization; same sender key replay; another participant cannot read the sender's receipt; outsider gets 404; retention purge removes receipt. |
| `POST /api/mobile/v1/consultations/{case_id}/attachments` | Reuses web upload handler; checks participant, block, case state, file signature/size and idempotency; same bytes/key replay one message; changed bytes conflict; failed/unsupported uploads create no message. |
| `GET /api/mobile/v1/consultations/{case_id}/attachments/{message_id}` | Case participant + message-to-case relation + non-deleted inbox state; private no-store, nosniff; outsider and cross-case IDs return 404. |

## Change in this pass

The attachment POST adapter previously returned the web handler's JSON payload without setting the same explicit private response policy used by its attachment GET and receipt endpoints. It now sets `Cache-Control: private, no-store`, `Vary: Authorization`, and `X-Content-Type-Options: nosniff` before dispatching the web handler. This is limited to response handling; the web handler remains authoritative for message persistence and lifecycle.

Regression assertions were added to:
- `tests/test_mobile_chat_actions.py`: attachment POST privacy headers and message receipt authorization variance.
- `tests/test_mobile_patient_parity.py`: patient media upload and receipt private response headers.
- `tests/test_mobile_analysis_upload_receipt.py`: analysis receipt private response headers.

These test modules are already included in the Security Recovery Python test command in `.github/workflows/security-recovery.yml`.

## Validation boundary

The code and test changes are committed to the feature branch. A new branch-head workflow run must execute before any test pass is claimed. The current GitHub integration can read Actions runs and logs but does not expose a workflow-dispatch action; if the PR event does not start Security Recovery, repository Actions must be dispatched by an authorized maintainer. No main merge, live deployment, migration, or patient-data mutation was performed.
