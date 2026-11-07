# Expert social profile implementation plan

Goal: Extend the existing verified-expert profile with member-only posts, moderated interactions and structured publications, without changing consultations or verification.

Architecture: Register a separate FastAPI router using the existing user/session, administrator MFA, SQLModel engine, shared rate buckets and private R2 services. Add independent social schema readiness to the existing release migration (baseline revision 12 remains compatible with other workers). No main merge or deployment.

Source baseline: feature/expert-publications-feed-20261107, e910fe9a397d2172a14fdb7decf0e308c635d107. User's supplied brief and image are the feature specification.

## Tasks

- [x] Add social models and serialized additive migration; verify repeated runs and missing-table readiness failures.
- [x] Add structured publication CRUD, normalized DOI uniqueness, public ORCID works parsing/sync, Crossref metadata suggestions. Preserve legacy publication text, label provenance without claiming authorship.
- [x] Add bounded SSRF-safe HTTPS fetching, metadata parsing and private, metadata-stripped JPEG/PNG/WebP upload. All images require human review in this first release; no sensitive-content transfer to AI providers.
- [x] Add member-only post CRUD, idempotency, pinning, optimistic versions, cursor feeds, idempotent likes, moderated comments/replies and reports. Lock expert/profile or post rows for concurrent mutations. Reuse distributed database admission counters.
- [x] Add administrator MFA-only queue, reports and append-only decision history, version checked approval/rejection and authenticated media access.
- [x] Add scoped responsive profile tabs, bottom-sheet composer, persistent text drafts, upload previews/reordering, removable link cards, publication forms and inline comments. Keep profile metrics and consultation CTA above the social section; preserve legacy profile refresh events.
- [x] Run endpoint and security regressions; run existing expert/consultation/storage tests; exercise 360/390/430px browser flows including reload, retries and consultation link. Document exact results and remaining external-service/device limitations.

## Review focus

Private/media addresses after redirects or DNS changes must never be fetched. Pending post/comment media must not leak. Edits invalidate moderation and old review decisions. Duplicate DOI/idempotency conflicts must be database enforced. Revoked/suspended experts cannot publish or gain access by passing another user's IDs.

## Execution notes

Detailed user specification already authorizes implementation choices and continuous execution. No additional product approval step is needed. Images are held for human review because automatic clinical identity detection is not dependable; this is deliberately conservative. ORCID import is an explicit operation, not an unimplemented automatic-sync switch. No fake counts or follow system.

Implementation, targeted verification and independent review completed. Live ORCID/Crossref access, actual R2 integration and physical iOS/Android keyboard testing remain external validation gates; see docs/expert_social_2026-11-07.md. No merge/deploy.
