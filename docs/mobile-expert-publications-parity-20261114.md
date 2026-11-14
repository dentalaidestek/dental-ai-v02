# Native expert public profile and structured publications

Continues PR #257 / issue #258. Baseline `ce366839`; concurrent patient-media destructive-retry protection through `87fd2d9f` is retained. No main merge, production deployment, store publication or replacement installed APK.

## Confirmed missing flows

The native ExpertProfile route mounted a feed-only DentalFlow view: name, counts and posts. It omitted the existing web public identity/biography/price/performance hero and publication/about tabs. The native account's legacy publication text field did not implement structured publication CRUD, DOI matching or ORCID importing. The expert directory also disabled an entire card for a busy expert and routed available cards directly to request creation, so a busy expert's public profile could not be opened there.

The adaptation uses `expert_public_profile.html`, `expert_profile_edit.html`, the existing expert-social publication endpoints and their canonical verification, moderation, version, deduplication and ownership rules. It does not replace these with a second publication backend.

## Web-to-native mapping

| Web behavior | Native implementation |
|---|---|
| Public identity hero | Verified display-name helper, authorized profile photo, specialty/institution, biography, academic verification, availability, price, real performance aggregates and all four social counters |
| Member-only verified profile | New `/api/mobile/v1/experts/{id}` uses the same verified-expert, account/block, intake-policy and capacity helpers; private/no-store response, no credential path or phone exposure |
| Follow / support / own management | Follow state refresh, server-derived intake availability, patient context retained into request entry, own native management route |
| Directory → profile | Busy profiles can be opened; support remains controlled by the canonical intake check |
| Posts / publications / about | Native tabs with the existing feed/comments/composer retained; about separates legacy declared academic text from structured papers |
| Publication list | Virtualized 30-item cursor pages, author/year/journal/DOI/description/source/status, owned moderation explanation, source link and retry/empty states |
| Manual publication | Native complete form using existing POST endpoint; duplicate constraints remain server-side |
| Edit / delete | Existing version sent for PUT; server conflicts and ownership errors retained; destructive deletion confirmation |
| DOI lookup | Existing Crossref endpoint fills draft and keeps match_id; user reviews and explicitly saves; canonical metadata comparison decides DOI_MATCH provenance |
| ORCID sync | Existing import endpoint, explicit action and write lock, HTTP-200 ok:false correctly treated as failure, persisted sync status reload and bounded RUNNING polling |
| Publication → Dental Flow | Existing share-preview endpoint, preview_id and canonical link, explicit share text and stable in-memory idempotency key; real post creation |

The public hero and tabs scroll with the list instead of consuming a fixed large top area on small screens. Existing post/reply/image menus and composer remain in SocialScreens. A publication/source link never receives a bearer token. Photos use the existing first-party social image authorization helper.

## Failure and security behavior

- Backend owns verification, active-account/block policy, case capacity, publication ownership, moderation, duplicates and edit versions. Native hidden buttons are not the authorization boundary.
- New public metadata never serializes phone numbers or credential locations. Confirmed academic title comes from `expert_display_name`, not an arbitrary name prefix or ORCID identity.
- Metadata and publication reads are account/profile scoped; delayed previous-account responses are ignored. Pending publication writes block tab/navigation changes and repeated taps.
- Unknown create/import/share results freeze automatic resubmission and direct the user to inspect server state; definite validation/conflict messages retain the editor. Publication drafts and share idempotency keys are in memory only, not durable across process death.
- ORCID RUNNING status is checked at five-second intervals, bounded to 24 polls. The backend still uses its existing request-bound import and persisted sync row, not a newly invented durable job queue. A timeout can leave a persisted RUNNING state; manual reconciliation remains necessary.
- Existing delete has no version contract and was not falsely given an atomic edit/delete guarantee. PostgreSQL simultaneous-edit/load acceptance remains open.

## Verification

Final verification: TypeScript passed; **240 Node tests passed, 0 failed** (18 session, 46 realtime, 176 beta). Selected Python suite: **208 passed, 0 failed** (350 deprecation warnings). Bare Python suite: **261 passed, 7 failed, 5 skipped** (562 deprecation warnings). Both Android/iOS Expo-Hermes exports succeeded. Commit and remote CI status are recorded in PR #257 / issue #258.

- `npm --prefix mobile test`: TypeScript plus all configured session/realtime/beta tests; includes retained concurrent patient-media guard coverage.
- Ten new native cases exercise update version/provenance, malformed pages/ORCID failure, actual manual editor and duplicate taps, read-only visibility, share preview/idempotency, DOI-populated editor, public profile/support/patient context, stale account reads, busy directory navigation and actual ORCID button/state refresh.
- Five new backend cases exercise verified public metadata/intake/privacy, policy/verification/authentication, blocked/inactive visibility, real native-bearer publication duplicate/version/edit/delete ownership, and the full five-case intake capacity boundary.
- Selected boot/account/program/patient/media/chat/request/admin/security/social regressions are run separately. Template-rendering fixtures are used for earlier account tests; new public-profile and publication flows execute real handler/database logic.
- Bare Python suite is also run. Existing six Chromium cases cannot launch because socket creation is denied; `test_following_page_loads_one_feed_with_working_member_actions` expects missing `/tmp/chromium`. The six cases are `test_mobile_profile_composer_publication_and_member_flow` at 360/390/430/1280, `test_four_images_upload_reorder_offline_retry_and_pending_visibility`, and `test_management_inline_editor_tabs_and_settings`. PostgreSQL cases without a configured database skip. No expectations deleted or weakened.
- Final Android/iOS Expo-Hermes exports are checked after concurrent source is restored. These are JavaScript exports, not signed native builds or real-device verification.

## Remaining acceptance and original scope

New metadata endpoint is not deployed; source changes do not alter the installed APK. No production Crossref/ORCID import, physical Android/iOS, authenticated two-account device, keyboard/background/network interruption, pixel equality, push delivery, PostgreSQL concurrency or 60,000-user capacity certification.

Own follower/following list drawers and detailed expert performance/settings remain separate gaps. Clinical AI result/review parity, full voice examination, Academic AI and remaining original headings still require their own web/native comparison and acceptance. P0 CI/API/session/device release gates remain open. The complete scope stays in `mobile-web-parity-tracker-20261114.md`; no whole-application completion claim is made.
