# Native clinical-media vault recovery and admission — 2026-11-16

## Web-first comparison

Re-read `app/templates/patient_detail.html` and the `/patients/{patient_id}/media` web handler before changing native behavior. The web path admits a whole archive batch with a 12-file limit, validates actual multipart bytes against the 96 MiB batch budget, stores the sanitized image, and exposes per-image preview/delete plus a destructive delete-all confirmation. Native keeps the same patient-scoped gallery and upload intent but sends files sequentially with durable per-file receipts and one stable batch ID.

The native picker already rejects known per-file and aggregate sizes. A gap remained in the encrypted staging boundary: when a picker omitted `fileSize`, `encryptClinicalMediaFile` copied the source into plaintext cache before checking the copied byte count. A known oversized source could therefore consume cache I/O before rejection. The vault source also contained a malformed `copyAsync` object literal; this was corrected while adding the preflight.

## Changes

- Query the source URI's real file metadata before plaintext staging. If the provider reports a finite size, reject empty or oversized files before `copyAsync`.
- Preserve compatibility with Android content providers that cannot stat an opaque URI: they fall back to the existing staged-file byte check, which remains authoritative before encryption.
- Add patient-scoped encrypted-vault reconciliation. After a pending intent has been parsed and migrated, only encrypted URIs referenced by that intent are retained; unreferenced `.dai` files left by process death are deleted.
- Run the same reconciliation after each durable pending-intent update, including successful per-file receipt reconciliation and explicit draft clearing.
- Invalid retained paths fail closed. A directory-listing failure leaves files untouched. Cleanup never scans another user or patient directory and never deletes the OS picker source.

## Crash-window behavior

- Process death before the pending intent is persisted: the encrypted file is an orphan and is removed on next visit to that patient.
- Process death after intent persistence but before upload: the referenced encrypted file is retained and can resume.
- Server accepted a file but the response was lost: the durable request key and batch ID remain; the server receipt is checked before any retry, and the now-unreferenced encrypted file is removed only after the updated intent is persisted.
- Process death between intent update and file deletion: next visit removes the orphan without touching the remaining pending files.

## Regression coverage added

- Oversized source is rejected before plaintext cache copy.
- Unknown Android content-provider stat falls back to staged-byte validation.
- Orphan deletion retains referenced files and never crosses patient scope.
- Invalid retained references and directory-listing failures fail closed.
- Native restore and durable draft mutation are wired to the cleanup helper.

The tests are registered through the existing `mobile/tests/clinicalMediaVault.cjs` entry in `npm run test:beta`. They were added to the branch but could not be executed in this connector-only run; no Node or TypeScript pass is claimed.

## Remaining acceptance

- Android/iOS physical-device tests are still required for `file://` and opaque `content://` metadata behavior, app termination at each crash window, and low-storage conditions.
- Full `npm ci`, `npm run typecheck`, `npm run test:beta`, Python security regressions and APK build remain blocked until GitHub Actions allocates a runner.
- No schema change, production deploy, main merge, APK/IPA publication, provider change or patient-record mutation was made.


## Vault purpose isolation follow-up

A second cross-module review found that archive and AI-analysis drafts share the same encrypted-vault utility but have different SecureStore intent keys. A broad patient-directory cleanup could therefore mistake an in-progress AI-analysis image for an orphaned gallery upload. Closed this by separating new files into `archive/` and `analysis/` subdirectories under the same user/patient scope. The URI validator accepts only the legacy root layout or these two explicit purpose directories. Archive cleanup scans only `archive/`; it preserves analysis drafts and all legacy root-level files. New archive and analysis encryption callers now declare their purpose.

Legacy root-level encrypted files are intentionally not swept by the new archive cleanup. This avoids guessing which older app intent owns them; they remain readable/deletable through the backward-compatible URI validator and can be cleaned only by their owning receipt workflow.
