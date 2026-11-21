# Mobile AI analysis refresh and payload contract

## Web flow reviewed

The web composer in `app/templates/analysis_new.html` creates an analysis from new files, selected patient-archive media, and optional tooth/clinical context. The patient detail page exposes batch selection from the clinical media archive and forwards the selected media IDs into the composer.

The web viewer in `app/templates/analysis_viewer.html` uses durable `WorkJob` records for VISION, PRELIMINARY, and FINAL stages. Failed jobs can be retried and active jobs can be cancelled through the owner-authenticated `/jobs/{job_id}/retry` and `/jobs/{job_id}/cancel` actions.

## Native flow reviewed

- `NativePatientMedia` already mirrors the web archive selection flow and passes selected media IDs to `NativeAnalysisUpload`; it does not re-upload those stored files.
- `NativeAnalysisUpload` keeps new image files in the encrypted local draft vault and reconciles ambiguous upload receipts before retrying.
- `NativeClinicalReview` is the canonical native workspace for the saved clinical result, durable job status, retry/cancel controls, and `NativeVisionViewer`.
- `mobile_clinical_api.py` checks analysis ownership and the job's analysis resource before forwarding retry/cancel to the existing web work handlers.

## Changes in this branch

1. The analysis metadata endpoint no longer reads the result object or returns a duplicate raw `ai_result`. The clinical workspace endpoint remains the single source for the bounded, validated result used by the native clinical review. This avoids a second object-storage read and a second large result payload on initial restore and metadata refresh.
2. The parent analysis screen no longer runs its own VISION/PRELIMINARY/FINAL polling loop. `NativeClinicalReview` owns foreground/focus-aware polling and publishes only the matching analysis/patient status, job, and image-vision flags back to the parent.
3. App resume, realtime updates, and a newly started clinical AI job request a refresh from that single workspace poller. Hidden clinical screens defer realtime refresh until focused.
4. A normal AI-start response must contain a positive durable `job_id`. The backend's idempotent `AI_ANALYZED` response is accepted without creating a duplicate job.
5. Regression coverage now checks metadata data minimization, cross-analysis job-action denial, job-receipt validation, parent/child refresh synchronization, and the absence of duplicate parent detail fetches.

## Validation boundaries

The new Python and Node tests are included in existing test files already referenced by the repository's mobile/security test commands. They were added but not executed in this automation run.

The current branch's latest commit has no GitHub check runs. The Android and security workflows remain manual-only while the earlier hosted runner failures are investigated. No workflow was dispatched to avoid restarting the previous notification storm. Full `npm test`, Android typecheck/APK, and backend pytest therefore remain unverified.

No main merge, production deploy, database migration, or patient-record mutation was performed.
