"""Offline ASGI burst benchmark: real voice route/core, simulated Claude transport.

No network listener, production database, real credentials or real provider I/O.
The existing raw-core benchmark remains useful as a fail-fast baseline; this
script measures the HTTP admission layer added above it.
"""
import argparse
import asyncio
import json
from pathlib import Path
import statistics
import time
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from app import voice_exam
from benchmark_voice_flow import dialogue, simulated_transport


def percentiles(values):
    values = sorted(values)
    return None if not values else {'p50_ms': round(statistics.median(values), 3),
        'p95_ms': round(values[min(len(values)-1, int(len(values)*.95))], 3)}


async def burst(concurrency, attempts=100):
    app = FastAPI(); app.include_router(voice_exam.router)
    _, text = dialogue()
    limiter = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://synthetic.local') as client:
        async def request(owner):
            async with limiter:
                start = time.perf_counter()
                response = await client.post('/patients/1/voice-exam/text',
                    headers={'x-synthetic-owner': str(owner)},
                    json={'transcript': text, 'consent': True})
                body = response.json()
                if response.status_code not in (200, 429):
                    raise RuntimeError('Unexpected synthetic benchmark response')
                if response.status_code == 200:
                    assert body['review']['fields']['age']['value'] == '32'
                else:
                    assert body['code'] == 'VOICE_QUEUE_BUSY'
                return response.status_code, (time.perf_counter()-start)*1000
        start = time.perf_counter()
        responses = await asyncio.gather(*(request(owner) for owner in range(1, attempts+1)))
    accepted = [elapsed for status, elapsed in responses if status == 200]
    rejected = [elapsed for status, elapsed in responses if status == 429]
    return {'concurrency': concurrency, 'attempts': attempts, 'completed': len(accepted),
        'queue_busy': len(rejected), 'completed_latency': percentiles(accepted),
        'busy_latency': percentiles(rejected), 'batch_wall_ms': round((time.perf_counter()-start)*1000, 3)}


def local():
    results = []
    with patch.object(voice_exam, '_access', lambda request, patient_id:
        (SimpleNamespace(id=int(request.headers['x-synthetic-owner'])), 'revision', None)):
        for concurrency in (1, 10, 50):
            with simulated_transport(.02) as stats:
                result = asyncio.run(burst(concurrency))
                result.update(provider_calls=stats['calls'], provider_peak_inflight=stats['peak_inflight'])
                assert stats['peak_inflight'] <= 2
                assert stats['calls'] == result['completed']
                results.append(result)
    return {'scope': 'LOCAL ONLY. Actual ASGI voice route, real extraction/normalizers; supplied model output and artificial 20 ms provider delay. Not production capacity, real AI/audio accuracy, or PostgreSQL performance.',
            'queue': {'active': 2, 'max_waiters': 8, 'wait_timeout_seconds': 30, 'persistence': 'none'}, 'bursts': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    encoded = json.dumps(local(), ensure_ascii=False, indent=2)
    if args.output: args.output.write_text(encoded+'\n')
    print(encoded)
