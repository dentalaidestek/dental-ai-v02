# Finish-only live examination

The main live microphone path now retains completed transcription segments in the open browser page. It does not call clinical extraction during listening or pause. The Finish button waits for provider flush, then extracts clinical context and verified closed taxonomy topics in bounded chunks, retrieves sources and runs the existing final review. Alternative 90-second clips now also request transcription only and append to the same draft; clinical extraction is deferred to the explicit evaluation/Finish action. Legacy API clients without the new header keep the old response contract.

## Draft lifecycle

- Full transient transcript: at most 72,000 JavaScript characters / 216,000 UTF-8 bytes accepted for processing. New listening is blocked at 60,000 / 180,000 to leave space for buffered final speech.
- Extraction chunks: at most 12,000 characters / 36,000 bytes, split losslessly at whitespace where possible. The existing 24 KB structured-context cap remains separate. Over-limit context reports an error and retains the transcript; it is never silently truncated.
- Successful chunk cursor survives extraction failures in the open page. Final-review retry does not repeat extraction. Editing/replacing transcript invalidates extraction checkpoints. Editing extracted fields invalidates the final result and preserves clinician edits.
- No browser or server transcript persistence. Discard, save or navigation clears transient data; unsaved navigation warns. Closed/reloaded pages cannot recover the transcript. Failure recovery is only within the open page.
- A normal short examination uses one extraction plus one final review, excluding transcription. Longer examinations need additional extraction calls. Unchanged partial-source retries skip the final model using a fingerprint bound to clinical context, prompt, model and public evidence (excluding retrieval timestamps). Total source outages stop before the final model. Explicit retry of an ambiguous provider/network timeout may still incur another provider charge; this change does not provide server-side idempotency.
- After pause or connection failure, an incomplete flush remains incomplete; pressing Finish cannot certify it. The server drains finalized segments for a bounded three-second window instead of closing after the first segment. An eight-second client watchdog exits a hung stopping state. This is a bounded heuristic, not proof of complete real-provider speech capture.
- No speech-triggered Finish command. An unconfirmed final flush requires the clinician to inspect the text and explicitly run evaluation.

## Closed source topics

Existing sixteen areas remain available. Five explicit endodontic topic IDs were added: instrument separation, root perforation, missed canal, postoperative pain and irreversible pulpitis. IDs are in the extraction schema enum and validated by the existing normalization/context contracts; original speech quotes are required. Fixed search strings are server-owned. No model-authored free-form literature query is introduced. The drug lookup still uses its existing validated ingredient vocabulary.

Topic selection is not diagnosis. Absent, historical or uncertain findings must not become confirmed patient findings. Unsupported conditions remain outside this bounded taxonomy. Real clinical recall and source-query quality have not been established by the software tests.

## Source retrieval

Fixed documents use 6 workers and at most 12 admitted jobs. Source groups use 4 workers and at most 8 admitted jobs. Shared outstanding document requests prevent duplicate fetches. Waiting ends after 12 seconds for documents / 16 seconds for groups; running threads cannot be forcibly killed and retain admission slots until completion. These are wait budgets, not an end-to-end execution guarantee. Local drug fallback and model review are separate stages.

Successful documents cache for one hour; failures cache for ten minutes. Total source excerpt text is bounded to 40,000 characters and final prompt+data to 80,000 characters. Omitted source text is reported as unavailable; grounding uses the same included excerpts. Existing keyword fallback, GDC communication selection, clinical prompt safeguards and response fields remain intact. Timing logs contain counts/durations rather than clinical text.

## Optional local PubMed catalogue

Default remains `VOICE_LITERATURE_MODE=remote`. For a pilot, build an offline snapshot with:

```sh
python -m scripts.build_voice_literature --db /persistent/literature.sqlite
```

Set `VOICE_LITERATURE_MODE=local` and `VOICE_LITERATURE_DB` only after reviewing and validating a populated catalogue. Local retrieval uses verified topic memberships ranked by evidence level/date; it never sends patient text to PubMed or falls back to network on a missing/corrupt index. This setting changes only the PubMed layer: other existing source groups can still make network requests.

Build uses all 21 closed topics and at most 200 relevant PubMed records per topic, without an arbitrary publication-date lower bound. Full abstract sections are retained; existing eligibility metadata still restricts clinical use. A complete replacement drops stale records and topic memberships. Transport/error envelopes or incomplete fetched PMID batches abort publication, preserving the previous file. All source metadata is a selection aid, not a guarantee of scientific quality or clinical applicability. A genuinely successful empty search can remove a topic; inspect the build report before rollout. Weekly scheduling and durable storage placement are operator rollout steps, not installed by this PR.

## Verification

197 Python tests and 11 Node controller/worklet/DOM harness files passed locally, using pinned web dependency versions for the tested subsystem. Tests include closed topics, source grounding, ownership/consent/atomic apply, lossless splits, checkpoint recovery, no mid-speech extraction, source queue/cache bounds, normal PubMed XML headers and error-batch protection. Two upstream deprecation warnings remain. All 11 harnesses passed on both the bundled Node v24.22.1 and a separately downloaded, SHA-256-verified official Node v26.12.1 runtime with jsdom 30.1.3. CI requests Node 26. Independent code review findings were repaired with regression tests.

This workspace contains the voice-subsystem snapshot, not every repository test. A dedicated PR workflow runs all voice Python tests and browser harnesses against the complete checkout. A direct synthetic fixed-topic PubMed ESearch attempt timed out in this runtime, and the hosted web fetch could not access the endpoint. Real microphone, actual model calls, full catalogue ingestion, clinical accuracy and production load are not verified here. A two-record real PubMed catalogue pilot was subsequently verified below. No production merge or deployment is performed.


## 2026-10-27 continuation verification

- Added bounded client request timeouts: final review 150 seconds; text/audio extraction and manual clinical review 120 seconds; other controller requests 30 seconds. Timeout errors preserve the open-page draft and release controls for explicit retry. These browser wait limits do not cancel remote provider work or guarantee charge-free retries after ambiguous timeouts.
- RED: the integrated DOM regression observed `/clinical` receiving 30,000 ms instead of the required 120,000 ms. GREEN: adding that endpoint to the extended budget passed the regression.
- Reproduced the full Python failure before isolation: 195 passed, two failed (`test_official_sources_do_not_use_academic_or_transfer_patient_data`, `test_sources_fail_closed_without_claiming_safety`). Synthetic concurrency results had polluted the shared document cache. The concurrency fixture now monkeypatches a fresh OrderedDict, in-flight dictionary and private 6/12 document and 4/8 group pools for each case, drains groups then documents before restoring patches, and leaves production source code unchanged.
- The new integrated jsdom harness renders the actual Jinja panel and loads both controllers plus the draft helper. It covers listen/pause/finish, duplicate Finish, approved save, disconnected recovery, unchanged/failed partial-source retry, extraction timeout draft retention/retry and the manual clinical deadline. This is simulated DOM/media/provider validation, not a real browser or microphone test.
- Synthetic source saturation cases at 1, 5 and 20 concurrent reviews passed. They test bounded admission/shared work, not real provider capacity or production load.
- The dedicated workflow installs jsdom 30.1.3, requests Node 26 and triggers on voice CSS changes as well as JavaScript changes. Panel script version is v15.
- Commands: `PYTHONPATH=.:../testdeps python -m pytest -q` → 197 passed, two dependency deprecation warnings; `PYTHONPATH=.:../testdeps NODE_PATH=../domdeps/node_modules node --test tests/voice*.cjs` → 11 passed, zero failed (Node v24.22.1); `git diff --check` passed.
- Chromium installation previously failed because the downloaded archive was corrupt. Real microphone/model end-to-end behavior, real PubMed catalogue ingestion and clinical accuracy remain unverified. Prior Actions runs failed before test steps; the cause is not established and remote CI is not claimed green. No merge or production deployment.


## 2026-10-27 follow-up: Node 26, real PubMed pilot and remote CI

- Downloaded official Node v26.12.1 and verified its archive against the release SHA-256 manifest before extraction. Re-ran all 11 Node harness files on that executable with jsdom 30.1.3: 11 passed, zero failed. Re-ran Python: 197 passed, two existing dependency deprecation warnings (4.81 seconds).
- Real network pilot used the existing builder with one closed topic (`endodontic diagnosis`) and `per_topic=2`, without patient input or model-generated search terms. ESearch/EFetch returned two eligible records, atomic SQLite publication succeeded and the read-only local retriever returned both with no unavailable markers. Retrieved IDs: `pubmed-37772327` (guideline), `pubmed-39206581` (systematic review). Both carried clinical-use metadata; clinical applicability was not independently reviewed. The temporary pilot database was deleted after verification. This verifies this small ingestion/retrieval path, not all 21 topics or the full 200-record-per-topic build; local mode remains opt-in.
- For remote commit `9d4d5a9f69abe81b45f046c63e339f7d3bcddc3e`, voice run `40459475190` failed in two seconds before any steps: `steps=[]`, `runner_id=0`, empty runner name. Academic and vision workflows also failed before test steps. Voice job logs return 404/BlobNotFound. The connector does not expose the check annotation endpoint, so the specific pre-run cause remains unconfirmed. No billing, quota or workflow-code cause is inferred; remote CI is still not green.
- A fresh Chromium download probe returned HTTP 200 with only 195 bytes of HTML, not a ZIP. No local browser binary was found. Real browser/microphone validation remains blocked. The existing review provider's API key and explicit model configuration are absent from this runtime; no actual model call was made and the provider connection was not changed.
- No source behavior changes, merge, deployment or production catalogue activation in this follow-up.
