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


## Follow-up — canonical web/native attachment contract

The web attachment handler previously checked only filename extension and byte limit, while the native adapter performed its own signature checks. The shared web handler now verifies image/document/audio signatures and sanitizes still images with the existing clinical-media sanitizer (including EXIF/XMP removal). The native adapter applies its stricter image byte and pixel caps before dispatching to that same handler.

Both attachment download paths now resolve the latest per-user inbox state instead of an arbitrary historical row. A locally deleted conversation no longer exposes an attachment through a stale direct URL. Web and native downloads use private no-store responses, the appropriate `Vary` header and `nosniff`.

The message receipt now echoes its exact case ID and client intent key. Native code rejects acknowledgements whose case/key differs from the pending upload, as well as malformed receipt payloads.

Added regressions cover web signature spoofing, metadata stripping, same-key replay/conflict, latest inbox state, cross-case message IDs, native receipt binding and PostgreSQL concurrent same-key attachment retries. The PostgreSQL concurrency test runs when `TEST_POSTGRES_URL` is configured by Security Recovery.

No production data or media were used. Changes remain on the feature branch; no main merge or live deployment was performed. Branch-head CI must complete before test success is claimed.

## Follow-up — attachment mutation and inbox-recovery gaps

A deeper pass across the native adapters and canonical web handlers found two gaps not covered by the original route table:

1. The web attachment handler accepts an empty `client_message_id` for browser compatibility. The mobile adapter also defaulted to an empty value, which meant a malformed/older native caller could create a non-idempotent attachment. The mobile route now requires a 16–96 character intent key and runs the web normalizer before reading multipart bytes. The native client already persists and sends this key; the browser handler remains backward-compatible.
2. The message-receipt endpoint checked case-wide retention but did not check the participant's latest `ConsultationInboxState`. The attachment download and web download both hide media while that participant has locally deleted the conversation. Receipt recovery now applies the same latest-state rule and returns 404 until that participant restores the conversation; it does not erase the pending local intent.

The mobile attachment adapter also performs a cheap preflight for closed case states and the WAITING_START deadline before reading the upload. The canonical web handler still repeats participant, block, case-state, retention, idempotency and persistence checks under the case lock; the preflight is not the authorization source of truth.

New/updated regression coverage:
- `tests/test_mobile_chat_actions.py`: mandatory/malformed key rejection, valid-key media upload coverage, replay/conflict and existing download privacy.
- `tests/test_mobile_chat_route_security.py`: latest-inbox-state receipt hiding and restoration, outsider/blocked upload denial, sender-scoped reuse of the same key, and post-commit response-loss recovery without a duplicate message.
- `.github/workflows/security-recovery.yml`: the new route-security module is part of the Python security job.

The analysis and patient-media receipt tests remain in the same security job and continue to cover patient ownership, exact payload replay/conflict, lost response recovery, and deleted-resource non-resurrection. The PostgreSQL parallel attachment retry remains covered by the existing concurrency test when `TEST_POSTGRES_URL` is configured.

Validation is pending for the branch head after these changes. Do not interpret source review or test additions as a test pass. No main merge, production deploy, schema migration, or patient-data mutation was performed.

## Follow-up — close the inbox-delete/upload race

The native adapter's preflight alone could race with a delete from another device while a large attachment was being read or written to object storage. The canonical web handler now checks the participant's latest inbox state both before reading the upload and again under the case lock immediately before message persistence. If the inbox was hidden during storage I/O, the staged object is deleted and no message/receipt is committed. This keeps the browser and native mutation path aligned and makes the web handler the authoritative lifecycle boundary.

Added two route-level regressions to `tests/test_mobile_chat_route_security.py`: direct web upload is rejected for a locally deleted inbox, and a synthetic cross-device delete inserted after storage but before the final locked transaction causes the staged object to be removed with no message row. These tests are included in the Security Recovery job through the previously added workflow entry.

No patient data, real attachments, main merge, production deploy, or schema migration was used.
