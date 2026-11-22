# Mobile live API compatibility check — 2026-11-22

## Scope

This is a source-level comparison between the deployed `main` snapshot inspected at
`7550add6453e9206e4b818d217c54ff39b1a1316` and
`feature/mobile-web-parity-20261110`. It is not a live authenticated API
smoke test. No merge, deployment, database migration, or patient-data operation
was performed.

## Confirmed route gaps behind the mobile 404 screens

The native client uses the following receipt and attachment routes. The
inspected `main` source does not register them; the feature branch does.

| Client operation | Required route | Feature-branch owner | Main snapshot |
|---|---|---|---|
| Reconcile a pending analysis upload before touching encrypted files | `GET /api/mobile/v1/analyses/uploads/receipt` | `app.mobile_analysis_api.upload_receipt` | Missing |
| Reconcile a pending clinical-media upload | `GET /api/mobile/v1/patients/{patient_id}/media/uploads/{request_key}` | `app.mobile_api.mobile_patient_media_upload_status` | Missing |
| Reconcile a pending chat attachment by its idempotency key | `GET /api/mobile/v1/consultations/{case_id}/message-receipt` | `app.mobile_api.mobile_consultation_message_receipt` | Missing |
| Upload a chat attachment | `POST /api/mobile/v1/consultations/{case_id}/attachments` | `app.mobile_api.mobile_chat_upload` | Missing |
| Open a chat attachment | `GET /api/mobile/v1/consultations/{case_id}/attachments/{message_id}` | `app.mobile_api.mobile_chat_attachment` | Missing |

The older `main` API still exposes `POST /analyses`, ordinary text-message
`POST /consultations/{case_id}/messages`, and basic patient-media routes.
Those are not substitutes for the receipt and attachment contracts above.
In particular, `mobile_modern_api_v3` on `main` has a legacy
`/consultations/{case_id}/media/{message_id}` handler, but the native
client requests the `/attachments/{message_id}` route.

## Mapping to the reported screens

- **AI analysis draft:** `analysisUploadReceipt()` calls
  `GET /analyses/uploads/receipt?patient_id=…&request_key=…` before any
  retry. Because that route is absent from the inspected `main` source,
  FastAPI returns a bare 404. The saved encrypted intent must remain on-device;
  it must not be deleted or replaced with a new request key while the server
  cannot reconcile it.
- **Expert-support attachment:** the composer restores a pending attachment
  with `GET /consultations/{case_id}/message-receipt` and sends through
  `POST /consultations/{case_id}/attachments`. Both are absent from the
  inspected `main` source. Ordinary text messages can still work, so
  this can appear as a partial chat failure rather than a complete outage.
- **Clinical-media archive:** the native archive also depends on its upload
  receipt route. A bare 404 there is a server-contract gap, not a reason to
  discard the encrypted draft.

## Branch safeguards added

- Bare FastAPI `404 Not Found` responses now use one shared message that points
  to a missing/older server API route; resource-specific 404 details such as
  `Hasta bulunamadı` remain distinct.
- The clinical-media uploader classifies a missing receipt route as a
  configuration failure, preserves the encrypted draft, and blocks a new
  upload attempt until reconciliation is available.
- The chat attachment composer blocks retries when its send/receipt route is
  missing and retains the same pending idempotency key.
- The analysis composer identifies the missing analysis receipt route, keeps
  the saved encrypted intent, and changes the action to a receipt recheck rather
  than suggesting that the user clear the draft.
- A route-registry regression now checks that the analysis, media, and chat
  receipt/attachment handlers are mounted exactly once and retain patient or
  case ownership checks.
- The clinical-media select-all control now matches the web gallery: a partial
  selection selects the first capped set; only a full target-count selection
  clears it.

## Release gate

1. Keep `main` and production unchanged until PR checks and review pass.
2. Merge/deploy the backend route set before expecting these mobile flows to
   work against production.
3. Run authenticated smoke tests for every route above, including wrong-owner
   cases, missing receipts, same-key retries, and attachment download privacy.
4. Build the APK from the exact reviewed commit after the backend is ready.
5. Do not ask users to delete pending drafts to work around a missing receipt
   endpoint. The server must first be able to reconcile the original key.

**Status:** this document records a verified source-level blocker. It does not
claim that production routes have been fixed or that a live deploy has occurred.
