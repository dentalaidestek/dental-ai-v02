"""Real HTTP burst handling plus bounded, ephemeral admission lifecycle."""
import asyncio
from contextlib import suppress
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app import voice_exam as voice
from test_voice_benchmark import benchmark_module


def test_eight_distinct_http_text_requests_wait_instead_of_failing_at_two(monkeypatch):
    monkeypatch.setattr(voice, '_access', lambda request, patient_id:
                        (SimpleNamespace(id=int(request.headers['x-synthetic-owner'])), 'revision', None))
    app = FastAPI()
    app.include_router(voice.router)
    benchmark = benchmark_module()
    _, text = benchmark.dialogue()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://synthetic.local') as client:
            return await asyncio.gather(*[client.post('/patients/1/voice-exam/text',
                headers={'x-synthetic-owner': str(owner)}, json={'transcript': text, 'consent': True})
                for owner in range(1, 9)])
    with benchmark.simulated_transport(.025) as stats:
        responses = asyncio.run(scenario())
    assert [r.status_code for r in responses] == [200] * 8
    assert all(r.json()['review']['fields']['age']['value'] == '32' for r in responses)
    assert stats['calls'] == 8  # Once per accepted request, no paid retries.
    assert stats['peak_inflight'] <= 2


def test_queue_preserves_fifo_and_rejects_excess_or_duplicate_owner():
    from app.voice_work_queue import VoiceWorkQueue, VoiceQueueBusy
    async def scenario():
        queue = VoiceWorkQueue(capacity=1, max_waiters=2, wait_timeout=1)
        release = asyncio.Event()
        entered = []
        async def work(owner):
            async with queue.slot(owner):
                entered.append(owner)
                if owner == 1:
                    await release.wait()
        first = asyncio.create_task(work(1)); await asyncio.sleep(0)
        second = asyncio.create_task(work(2)); await asyncio.sleep(0)
        third = asyncio.create_task(work(3)); await asyncio.sleep(0)
        with pytest.raises(VoiceQueueBusy):
            async with queue.slot(4): pytest.fail('full queue must not execute work')
        with pytest.raises(VoiceQueueBusy):
            async with queue.slot(1): pytest.fail('same owner must not execute duplicate work')
        release.set()
        await asyncio.gather(first, second, third)
        assert entered == [1, 2, 3]
        async with queue.slot(4): pass
    asyncio.run(scenario())


@pytest.mark.parametrize('cancel_after_grant', [False, True])
def test_cancelled_waiter_returns_admission_to_next_request(cancel_after_grant):
    from app.voice_work_queue import VoiceWorkQueue
    async def scenario():
        queue = VoiceWorkQueue(capacity=1, max_waiters=2, wait_timeout=1)
        entered = []
        async def work(owner):
            async with queue.slot(owner): entered.append(owner)
        async with queue.slot(1):
            waiter = asyncio.create_task(work(2)); await asyncio.sleep(0)
            next_waiter = asyncio.create_task(work(3)); await asyncio.sleep(0)
            if not cancel_after_grant: waiter.cancel()
        if cancel_after_grant: waiter.cancel()
        with suppress(asyncio.CancelledError): await waiter
        await asyncio.wait_for(next_waiter, 1)
        assert entered == [3]
        async with queue.slot(2): pass  # Owner registration was also removed.
    asyncio.run(scenario())


def test_timed_out_waiter_never_runs_and_owner_can_try_again():
    from app.voice_work_queue import VoiceWorkQueue, VoiceQueueBusy
    async def scenario():
        queue = VoiceWorkQueue(capacity=1, max_waiters=1, wait_timeout=.01)
        async with queue.slot(1):
            with pytest.raises(VoiceQueueBusy):
                async with queue.slot(2): pytest.fail('timed-out work cannot execute')
        async with queue.slot(2): pass
    asyncio.run(scenario())


def test_provider_failure_releases_capacity_without_retry():
    from app.voice_work_queue import VoiceWorkQueue
    async def scenario():
        queue = VoiceWorkQueue(capacity=1, max_waiters=1, wait_timeout=1)
        with pytest.raises(RuntimeError):
            async with queue.slot(1): raise RuntimeError('synthetic provider failure')
        async with queue.slot(2): pass
    asyncio.run(scenario())


def test_repeated_http_cancellation_keeps_slot_until_worker_finishes():
    import threading
    from app.voice_work_queue import VoiceWorkQueue, VoiceQueueBusy, run_voice_worker
    started, release = threading.Event(), threading.Event()
    calls = []
    def operation():
        calls.append('started')
        started.set()
        assert release.wait(2)
        calls.append('finished')
    async def connected(): return False
    request_scope = SimpleNamespace(is_disconnected=connected)
    async def scenario():
        queue = VoiceWorkQueue(capacity=1, max_waiters=0, wait_timeout=1)
        async def request():
            async with queue.slot(1): await run_voice_worker(request_scope, operation)
        task = asyncio.create_task(request())
        while not started.is_set(): await asyncio.sleep(.001)
        try:
            task.cancel(); await asyncio.sleep(0)
            task.cancel(); await asyncio.sleep(0)
            with pytest.raises(VoiceQueueBusy):
                async with queue.slot(2): pytest.fail('worker still owns capacity')
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError): await task
        async with queue.slot(2): pass
    asyncio.run(scenario())
    assert calls == ['started', 'finished']


@pytest.mark.parametrize('endpoint', ['audio', 'text', 'finalize', 'clinical'])
def test_http_busy_response_never_calls_provider(monkeypatch, endpoint):
    from app.voice_work_queue import VoiceWorkQueue
    queue = VoiceWorkQueue(capacity=1, max_waiters=0)
    monkeypatch.setattr(voice, '_access', lambda *args: (SimpleNamespace(id=1), 'revision', None))
    app = FastAPI(); app.include_router(voice.router)
    app.state.voice_work_queue = queue
    async def scenario():
        async with queue.slot(9):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://synthetic.local') as client:
                if endpoint == 'audio':
                    return await client.post('/patients/1/voice-exam/audio', content=b'\x1aE\xdf\xa3' + b'x' * 100,
                        headers={'x-voice-consent': 'yes', 'content-type': 'audio/webm'})
                data = {'transcript': 'Örnek', 'consent': True} if endpoint == 'text' else {'context': {}, 'consent': True}
                return await client.post('/patients/1/voice-exam/' + endpoint, json=data)
    monkeypatch.setattr(voice.core, 'extract', lambda **kw: pytest.fail('no provider work while full'))
    response = asyncio.run(scenario())
    assert response.status_code == 429
    assert response.headers['retry-after'] == '2'
    assert response.json()['code'] == 'VOICE_QUEUE_BUSY'
    assert 'Taslak korunuyor' in response.json()['error']


def test_disconnected_request_never_starts_provider_work():
    from app.voice_work_queue import run_voice_worker, VoiceQueueBusy
    async def disconnected(): return True
    async def scenario():
        with pytest.raises(VoiceQueueBusy):
            await run_voice_worker(SimpleNamespace(is_disconnected=disconnected),
                                   lambda: pytest.fail('closed request cannot start work'))
    asyncio.run(scenario())


def test_two_stalled_audio_uploads_do_not_occupy_text_processing_slots(monkeypatch):
    monkeypatch.setattr(voice, '_access', lambda request, patient_id:
                        (SimpleNamespace(id=int(request.headers['x-synthetic-owner'])), 'revision', None))
    monkeypatch.setattr(voice.core, 'extract', lambda **kw: {'fields': {}})
    app = FastAPI(); app.include_router(voice.router)
    async def scenario():
        started = [asyncio.Event(), asyncio.Event()]
        async def stalled(index):
            started[index].set()
            yield b'x'
            await asyncio.Future()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://synthetic.local') as client:
            uploads = [asyncio.create_task(client.post('/patients/1/voice-exam/audio',
                headers={'x-synthetic-owner': str(i+1), 'x-voice-consent': 'yes', 'content-type': 'audio/webm'},
                content=stalled(i))) for i in range(2)]
            try:
                await asyncio.gather(*(event.wait() for event in started))
                response = await asyncio.wait_for(client.post('/patients/1/voice-exam/text',
                    headers={'x-synthetic-owner': '3'}, json={'transcript': 'Örnek', 'consent': True}), .5)
                assert response.status_code == 200
            finally:
                for task in uploads: task.cancel()
                await asyncio.gather(*uploads, return_exceptions=True)
    asyncio.run(scenario())


def test_audio_upload_deadline_returns_slot_without_calling_provider(monkeypatch):
    monkeypatch.setattr(voice, '_access', lambda *args: (SimpleNamespace(id=1), 'revision', None))
    monkeypatch.setattr(voice, 'AUDIO_UPLOAD_TIMEOUT', .01)
    monkeypatch.setattr(voice.core, 'extract', lambda **kw: pytest.fail('incomplete upload cannot call provider'))
    app = FastAPI(); app.include_router(voice.router)
    async def stalled():
        yield b'x'
        await asyncio.Future()
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://synthetic.local') as client:
            for _ in range(3):
                response = await client.post('/patients/1/voice-exam/audio', content=stalled(),
                    headers={'x-voice-consent': 'yes', 'content-type': 'audio/webm'})
                assert response.status_code == 408
                assert response.json()['code'] == 'VOICE_UPLOAD_TIMEOUT'
    asyncio.run(scenario())


def test_same_account_cannot_start_text_while_audio_is_uploading(monkeypatch):
    monkeypatch.setattr(voice, '_access', lambda *args: (SimpleNamespace(id=1), 'revision', None))
    monkeypatch.setattr(voice.core, 'extract', lambda **kw: pytest.fail('duplicate account operation cannot bill'))
    app = FastAPI(); app.include_router(voice.router)
    async def scenario():
        started = asyncio.Event()
        async def stalled():
            started.set()
            yield b'x'
            await asyncio.Future()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://synthetic.local') as client:
            upload = asyncio.create_task(client.post('/patients/1/voice-exam/audio', content=stalled(),
                headers={'x-voice-consent': 'yes', 'content-type': 'audio/webm'}))
            try:
                await started.wait()
                response = await client.post('/patients/1/voice-exam/text', json={'transcript': 'Örnek', 'consent': True})
                assert response.status_code == 429
            finally:
                upload.cancel()
                await asyncio.gather(upload, return_exceptions=True)
    asyncio.run(scenario())
