# Native support parity, CI repair and query fan-out — 2026-11-21

## Starting evidence

Starting branch HEAD: e1a28889661bbc15658c6fb13e9e10338ed659f6.

Before editing, inspected the latest PR-triggered workflows:

- Android run https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44883746560:
  - TypeScript failed because NativeSupportRequests.tsx referenced setLoading, setError, setSending, createKey, replyKey and their setters without declaring those state hooks.
  - Beta: 933/935. The optional case-link test asserted a string that the screen does not use, and the account-scope test used CommonJS require() directly on an ES-module TypeScript file, producing Unexpected token 'export'.
  - Session, realtime and Expo export steps passed. The internal APK job was still assembling at the time of inspection.
- Security Recovery https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44883746530 completed successfully, including Python/PostgreSQL and the existing native voice, clinical, academic, program and social jobs. It did not yet run the new native support/account-scope tests or tests/test_mobile_support_api.py.

The failed Android checks were source/test-harness failures, not runner-allocation failures. The Security Recovery result was green for the suites it actually included; it was not support-specific coverage.

## Web-first flow reviewed

Reviewed the branch versions of:

- app/templates/support_request.html
- app/templates/_support_status_regions.html
- app/main.py support page, fragment, create, conversation, reply and read routes
- app/mobile_api.py bearer-authenticated ticket, report, conversation-option and mutation routes
- mobile/src/NativeSupportRequests.tsx, mobile/src/modernApi.ts, mobile/src/supportDraftScope.ts and mobile/App.tsx

The web contract includes 160-character subject, 4,000-character message, optional private consultation association, owner-only ticket history, read-through acknowledgement, older-message paging, and one user reply per support turn. The native screen already had the corresponding features; this pass repairs its broken state declarations and makes the client reject malformed API pages/receipts.

## Changes

1. Declared the missing native loading/error/sending and pending idempotency-key state hooks. This resolves the exact TS2304/TS2552 names from the CI diagnostic artifact.
2. Corrected the case-link regression to assert the real case_id persistence/API argument. The helper test now transpiles supportDraftScope.ts to CommonJS with the installed TypeScript compiler before executing it in a VM; it no longer asks Node's CommonJS loader to parse a TypeScript ES module.
3. Strengthened support API runtime validation:
   - ticket/report/conversation page bounds and unique IDs;
   - descending ticket/report order and ascending message order;
   - monotonic, page-consistent cursors;
   - status, date, message, unread-count and receipt validation;
   - exact ticket ID checks on read/reply receipts;
   - request-key format validation before sending mutations.
4. Removed mobile support list/report/conversation N+1 query patterns:
   - latest ticket messages are fetched in one grouped query and one bounded IN query;
   - ticket/report unread counts use the existing web-shared _support_unread_map aggregate;
   - conversation message existence and counterpart users are fetched in batches.
5. Added backend regressions that fail if ticket/report list code falls back to per-ticket unread/reply queries, and that cap conversation-option message/user lookups independently of the number of cases.
6. Added a dedicated native-support-security job and included tests/test_mobile_support_api.py in Python/PostgreSQL Security Recovery.

## Commits

- 004b0aac — missing NativeSupportRequests state hooks
- 1df4de1a — TypeScript test loader and case-link assertion
- 4fc28a26 — strict support API page/receipt validation
- faa3a42c — batched support ticket/report/conversation queries
- 3ac63582 — batched-query regressions
- 212a855f — native and Python support security CI coverage

## Verification boundary

These changes are committed to feature/mobile-web-parity-20261110. The latest-head Android typecheck/beta, Android APK, and updated Security Recovery workflow must complete before this pass is considered green. The starting-head diagnostics were inspected from GitHub Actions artifacts; no local full npm/Python execution is claimed here.

No main merge, production deployment, database migration, APK/IPA publication, or real patient/support record mutation.
