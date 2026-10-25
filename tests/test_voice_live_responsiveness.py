"""Keep the ASGI event loop responsive during real provider lease SQL work."""
import asyncio
from contextlib import asynccontextmanager
import json
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import APIRouter
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from app import provider_budget, voice_exam, voice_exam_live


@pytest.mark.parametrize('phase,outcome', [
    ('acquire', 'success'), ('release', 'success'),
    ('acquire', 'provider_error'), ('release', 'provider_error'),
    ('acquire', 'cancel_stream'), ('release', 'cancel_stream'),
    ('acquire', 'cancel_acquire'),
])
def test_live_lease_database_wait_does_not_stall_other_requests(monkeypatch, phase, outcome):
    engine = create_engine('sqlite://', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine, tables=[provider_budget.ProviderCounter.__table__,
                                                provider_budget.ProviderSlot.__table__])
    monkeypatch.setattr(provider_budget, '_engine', lambda: engine)
    monkeypatch.setattr(provider_budget, '_limits', lambda *args: [])
    monkeypatch.setenv('STUDY_ROUTER_REQUEST_BUDGETS_JSON', '{}')
    monkeypatch.setenv('DENTAL_PROVIDER_MAX_INFLIGHT', '4')
    monkeypatch.setenv('VOICE_EXAM_ENABLED', '1')
    monkeypatch.setenv('VOICE_EXAM_LIVE_ENABLED', '1')
    monkeypatch.setenv('GEMINI_API_KEY', 'SYNTHETIC_NOT_A_KEY')
    monkeypatch.setattr(voice_exam, '_access', lambda *args: (SimpleNamespace(id=98765), 'revision', None))
    waiting = threading.Event()
    finished = threading.Event()
    progressed = []

    def slow_sql(connection, cursor, statement, parameters, context, executemany):
        sql = statement.lower()
        matches = (sql.startswith('insert into providerslot') if phase == 'acquire'
                   else sql.startswith('delete from providerslot') and 'providerslot.token' in sql)
        if matches:
            waiting.set()
            time.sleep(.15)  # Simulate a slow real lease query, never a live database.
            finished.set()
    event.listen(engine, 'before_cursor_execute', slow_sql)

    @asynccontextmanager
    async def connection(*args, **kwargs):
        yield object()

    async def stream(socket, provider):
        await asyncio.sleep(0)
        if outcome == 'provider_error':
            raise RuntimeError('synthetic provider failure')
        if outcome == 'cancel_stream':
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

    import websockets.asyncio.client
    monkeypatch.setattr(websockets.asyncio.client, 'connect', connection)
    monkeypatch.setattr(voice_exam_live, 'proxy', stream)

    class Socket:
        headers = {'origin': 'https://dentalai.tr'}
        url = SimpleNamespace(scheme='wss', netloc='dentalai.tr')
        scope = {'type': 'websocket', 'path': '/', 'headers': [], 'server': ('dentalai.tr', 443), 'scheme': 'wss'}
        closed = False
        messages = []
        async def accept(self): pass
        async def receive_text(self): return json.dumps({'type': 'start', 'consent': True})
        async def close(self, **kwargs): self.closed = True
        async def send_json(self, body): self.messages.append(body)

    router = APIRouter()
    voice_exam_live.register_live(router)
    endpoint = router.routes[0].endpoint
    socket = Socket()

    async def scenario():
        task = asyncio.create_task(endpoint(socket, 1))
        cancelled = False
        while not task.done():
            if waiting.is_set() and not finished.is_set():
                progressed.append(True)
                if outcome == 'cancel_acquire' and not cancelled:
                    task.cancel()
                    cancelled = True
            await asyncio.sleep(.001)
        await task
    try:
        asyncio.run(scenario())
        assert waiting.is_set(), 'the real lease SQL was exercised'
        assert progressed, f'{phase} lease SQL blocked unrelated event-loop work'
        assert socket.closed
        assert 98765 not in voice_exam_live._active
        with Session(engine) as session:
            assert session.exec(select(provider_budget.ProviderSlot)).all() == []
        assert bool(socket.messages) is (outcome == 'provider_error')
    finally:
        engine.dispose()
