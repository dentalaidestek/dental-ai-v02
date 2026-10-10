# Membership verification

Profilim links to `/account/verification`, a three-step type / upload / review-and-submit flow. Supported documents are diploma, graduation certificate, TDB membership card and student certificate. JPG, PNG and unencrypted PDF files are accepted up to 5 MiB; server checks actual image format and parses PDFs (1–100 pages).

Submitting creates a private, pending application and a notification. `/admin/member-verifications` lists 25 applications per page. Administrators download the document, confirm identity checks to approve, or provide a rejection reason. Decisions produce an audit entry and a result notification. A student document displays student membership verification; this workflow never changes user roles or grants expert permissions. Existing expert verification remains separate.

Document download requires its owner or an administrator. Storage references are never put in public templates. Responses are attachments with `private, no-store`, `nosniff` and sandbox headers. Account erasure deletes application metadata and hands document references to the existing best-effort storage cleanup. The workflow adds no AI/provider calls.

An approved application becomes stale when the account name or professional title differs from the reviewed snapshot. Changed pending profiles cannot be approved until the administrator rejects the outdated application and the user resubmits. Rejected or stale applications permit a new upload. PostgreSQL locks the owner row before final submission and review to serialize duplicates; rejected race uploads are cleaned up outside the transaction.

Release migration revision 12 creates the table using the existing explicit migration command: `python -m app.migrate`. Run migration before starting web or worker processes. No production deployment was performed as part of this change.

Validation: 16 new feature tests cover four document types, owner/admin authorization, approval attestation, rejection/resubmission, changed identity, malformed and encrypted files, profile navigation, account erasure and erasure during upload. PostgreSQL CI additionally tests simultaneous uploads/reviews and repeatable migration from an absent table. Browser screenshot verification was unavailable locally because Chromium could not be downloaded in this environment; HTML rendering and JavaScript syntax were checked.
