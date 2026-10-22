# Synthetic one-minute voice-examination check

Fixture: `tests/fixtures/voice_exam_one_minute_tr.json` (120 words including speakers, approximately one minute). This is synthetic text, not recorded audio. Expectations cover symptoms, uncertain findings, history/allergies, treatment decisions, communication, barriers, appointment agreement and clinical-record privacy.

## Results, 2026-10-22

Real Gemini extraction and final review were **not run: no GEMINI_API_KEY in this environment**. None of the fixture expectations can therefore be marked as discovered by the model. Microphone, transcription accuracy and production Render latency remain unverified.

The actual extraction orchestration and validators ran against supplied synthetic provider output. Serial p50: 1.555 ms; p95: 3.209 ms. Unsupported source quotes were rejected. These timings exclude real inference, HTTP routing/authentication and database/distributed provider-budget work.

With artificial 20 ms provider latency, 100 requests per batch:

| Concurrency | Accepted | Busy | Accepted p95 |
| --- | --- | --- | --- |
| 1 | 100 | 0 | 28.796 ms |
| 10 | 2 | 98 | 23.403 ms |
| 50 | 8 | 92 | 38.294 ms |

The per-process two-request semaphore bounds provider pressure but rejects sudden bursts immediately. Accepted counts vary with thread scheduling; this is a saturation probe, not a sustainable-user-capacity estimate. Low process memory (23 MiB peak, 3 MiB growth) does not establish production capacity.

Separately, actual official-source access for the synthetic term metformin took 10.14 seconds cold and 0.02 ms cached. This cold retrieval can contribute substantial final-review latency; it is not Gemini latency. No additional drug corpus was added.

## Reproduce

```sh
python -m scripts.benchmark_voice_flow --local --real --sources --output /tmp/voice-benchmark.json
```

`--real` performs one extraction and one final review when credentials exist and may incur provider cost. Review returned outputs against fixture expectations. `--local` uses supplied output, simulated transport and a no-op database budget reservation. `--sources` independently accesses the official source. Raw measurements are in `voice_exam_benchmark_2026-10-22.json`. No production patient data or deployment is involved.
