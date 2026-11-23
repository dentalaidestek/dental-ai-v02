# Mobile parity CI cancellation root cause — 2026-11-20

## Evidence inspected before changing workflows

The PR head before this correction was `48a7d8f38ede902fabdaeeebbccee89bf806f482`.

Two current-head workflow runs were cancelled:

- Android run [44743258351](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44743258351), run number 4242.
- Security Recovery run [44743258322](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44743258322), run number 1940.

This was not a pre-runner provisioning failure. Both runs had real hosted runners, checkout and setup steps, and usable logs.

### Android cancellation

The Android `typecheck` job completed `npm ci` and started:

```text
> dental-ai-mobile@0.2.0 typecheck
> tsc --noEmit
```

Approximately ten seconds later the log recorded:

```text
##[error]The operation was canceled.
```

The job step summary reports `TypeScript typecheck: cancelled`; beta tests and Expo exports were skipped. The APK job was also cancelled while preparing its Gradle cache.

### Security Recovery cancellation

The native social, academic and program jobs were cancelled during dependency installation. Clinical and voice jobs were cancelled after installation, while their validation steps were running. The Python job was cancelled during OCR prerequisite installation; pytest and PostgreSQL validation were skipped.

The two workflows shared branch-scoped concurrency groups with `cancel-in-progress: true`. Each new commit pushed to the PR updated the same group and could cancel the active run before typecheck or security validation finished. The logs therefore do not demonstrate a source-code failure.

## Correction

Both workflows now use `cancel-in-progress: false` while retaining one branch-scoped concurrency group.

This lets an active validation finish. GitHub may replace an older pending run with the latest pending run for the same group, so the PR does not need to execute every intermediate commit's full test matrix.

A Python regression test, `tests/test_ci_concurrency_contract.py`, asserts that both workflows keep this policy. The Security Recovery pytest command runs that test.

## Validation boundary

The workflow files and regression test are committed. The new HEAD must still complete a fresh Android and Security Recovery run before any green result is claimed. The cancelled runs above are diagnostic evidence only; they are not test passes.

No patient data was accessed or changed. No migration, main merge, production deployment, APK publication or store release was performed.

## Separate privacy follow-up

The account-erasure coordinator still returns profile-photo and membership/expert-document storage references to the web handler, which attempts `storage_delete` after the database transaction. That caller logs deletion failures but does not enqueue a durable retry. Patient-linked clinical records remain intentionally retained pending the applicable retention/transfer policy. This storage-cleanup gap is not changed by the CI fix and remains a separate security task.
