# Native voice clinical extraction receipts — 2026-11-18

## Scope

The native client sends transcript chunks to the existing `/api/mobile/v1/patients/{id}/voice-exam/text` adapter. Before this change, a successful Claude extraction could finish on the server while the phone closed before its encrypted SecureStore checkpoint was written. Retrying the same chunk invoked Claude again.

This change adds a durable, owner- and patient-scoped receipt for each examination session/chunk. It reuses the existing `WorkJob` table and the dedicated `VOICE_ASR_RECEIPT_KEY`; no schema migration or new provider is introduced.

## Request identity

The client derives a stable request key from the persisted examination session ID and zero-based chunk index:

```text
<session-id-without-hyphens>_<chunk-index>
```

The client keeps the same session ID for a recovery retry. Manual transcript edits, an explicit recheck, or a patient-revision conflict use a fresh session ID. This prevents an old extraction from being reused for a materially new examination.

The server scopes the receipt by authenticated owner, patient and request key. It independently computes a keyed HMAC-SHA256 digest over canonical JSON containing the transcript chunk and normalized previous-chunk context. Reusing a key with different input returns 409 before provider invocation.

## Persistence and privacy

- WorkJob kind: `VOICE_CLINICAL_RECEIPT`, resource type: `PATIENT`.
- `source_hash` stores only the keyed input digest.
- `dedupe_key` is a SHA-256 hash of the owner/patient/request-key namespace.
- `payload_json` contains only an AES-GCM envelope; the review JSON and revision are encrypted with authenticated associated data binding owner, patient, dedupe key and digest.
- Raw audio, transcript, prior context, provider prompts, API keys and decrypted review are never copied to logs or plaintext WorkJob fields.
- Existing `VOICE_ASR_RECEIPT_KEY` is used through the same strict 32-byte hex loader; no fallback to the application secret is allowed.

## State transitions

| State | Meaning | Same-key behavior |
|---|---|---|
| PROCESSING | A lease owns the one provider attempt | 409 in progress; no second call |
| DONE | Encrypted review and revision persisted | Decrypt and replay; no provider call |
| RETRYABLE | Failure was typed before provider invocation | Bounded retry, at most five claims |
| FAILED | Provider outcome is ambiguous or invalid | Terminal unknown; no same-key retry |
| EXPIRED | 24-hour result TTL elapsed | 410; ciphertext replaced by tombstone |

The lease is 180 seconds. An expired PROCESSING lease is converted to terminal unknown rather than reclaimed, because the provider may already have completed and only the response/receipt write may have been lost. Only typed `VoiceBusy` and `VoiceConfigurationError` failures are marked retryable. Provider timeouts, parse failures, unexpected exceptions and persistence uncertainty are terminal for that key.

## Patient revision guard

The patient revision is read before the provider call and checked again after it. If the record changes while Claude is working, the result is not returned or cached as a valid current review; the receipt is tombstoned and the client is told to restart under a fresh session key. A completed receipt is also not replayed if the patient's current revision no longer matches the revision stored in that receipt.

## Retention and scale

The existing minute-throttled `prune_history` worker now expires this receipt kind alongside ASR receipts:
- encrypted result TTL: 24 hours;
- tombstone retention: 7 days;
- stale PROCESSING lease: terminal unknown;
- missing or no-longer-owned patient: delete receipt;
- bounded batch: 100 rows per cleanup pass.

The receipt is one small row per bounded text chunk, uses the existing indexed WorkJob infrastructure, and does not add polling, provider retries, a new database table or transcript search.

## Regression coverage added

- AES-GCM replay with no plaintext transcript/review in WorkJob payload;
- same key + changed transcript/context conflict;
- account/patient isolation;
- PROCESSING returns busy without a second claim;
- expired lease becomes terminal unknown;
- 24-hour TTL and tombstone;
- only typed pre-provider failures retry;
- unknown provider result is never retried with the same key;
- tampered ciphertext fails closed;
- lease ownership/expiry guard;
- patient deletion cleanup;
- HMAC input digest stability and context binding;
- mobile route replay, changed input, provider ambiguity, typed capacity retry, account isolation and patient-revision races;
- client request key stability for one session and separation across sessions.

## Verification boundary

The regression files and workflow steps are committed. This environment could not run the repository's Python/Node suites or dispatch the manual-only GitHub Actions workflows. A passing test result is not claimed. Android TypeScript, Expo export, Gradle and physical-device acceptance remain open until a GitHub runner or local checkout is available.
