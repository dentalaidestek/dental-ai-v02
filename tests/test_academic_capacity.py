"""Synthetic admission and owned-query tests; no production notes/model calls."""
import ast
import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Field, Session, create_engine, select, func

from app.request_limits import RequestLimits


async def request(app, path, *, method='POST', multipart=False, body=b'', headers=()):
    messages = []
    sent = False
    async def receive():
        nonlocal sent
        if sent:
            return {'type': 'http.disconnect'}
        sent = True
        return {'type': 'http.request', 'body': body, 'more_body': False}
    async def send(message):
        messages.append(message)
    scope = {'type': 'http', 'path': path, 'method': method, 'headers': list(headers) + (
        [(b'content-type', b'multipart/form-data; boundary=test')] if multipart else [])}
    await app(scope, receive, send)
    return next(m['status'] for m in messages if m['type'] == 'http.response.start')


def test_ai_burst_does_not_occupy_upload_lane_or_all_http_slots(monkeypatch):
    monkeypatch.setenv('DENTAL_MAX_HTTP_REQUESTS', '8')
    monkeypatch.setenv('DENTAL_MAX_UPLOADS', '1')
    monkeypatch.setenv('DENTAL_MAX_ACADEMIC_REQUESTS', '2')
    async def scenario():
        release, full = asyncio.Event(), asyncio.Event()
        active = 0
        entered = 0
        async def application(scope, receive, send):
            nonlocal active, entered
            if scope['path'].endswith('/ask-stream'):
                active += 1
                entered += 1
                if active == 2:
                    full.set()
                await release.wait()
                active -= 1
            await send({'type': 'http.response.start', 'status': 200})
            await send({'type': 'http.response.body', 'body': b'ok'})
        limited = RequestLimits(application)
        holds = [asyncio.create_task(request(limited, '/notes/courses/1/ai/ask-stream',
                                            multipart=True)) for _ in range(2)]
        await asyncio.wait_for(full.wait(), 1)
        assert limited.academic == 2 and limited.uploads == 0
        burst = await asyncio.gather(*[request(limited, f'/notes/courses/{course}/ai/ask-stream',
                                            multipart=True) for course in ['1', '01', '+1', '-1'] * 250])
        assert set(burst) == {503} and entered == 2
        assert await request(limited, '/notes/courses/1/materials', multipart=True) == 200
        assert await request(limited, '/patients', method='GET') == 200
        assert await request(limited, '/readyz', method='GET') == 200
        release.set()
        assert await asyncio.gather(*holds) == [200, 200]
        assert (limited.active, limited.academic, limited.uploads) == (0, 0, 0)
    asyncio.run(scenario())


def test_mobile_and_web_share_academic_lane_and_cancellation_releases_it(monkeypatch):
    monkeypatch.setenv('DENTAL_MAX_ACADEMIC_REQUESTS', '1')
    async def scenario():
        entered = asyncio.Event()
        async def application(scope, receive, send):
            entered.set()
            await asyncio.Event().wait()
        limited = RequestLimits(application)
        held = asyncio.create_task(request(limited, '/api/mobile/v1/academic/courses/1/ask'))
        await asyncio.wait_for(entered.wait(), 1)
        assert await request(limited, '/notes/courses/2/ai/ask') == 503
        held.cancel()
        with pytest.raises(asyncio.CancelledError):
            await held
        assert limited.active == limited.academic == limited.uploads == 0
    asyncio.run(scenario())


def test_question_body_bound_cannot_be_evaded_with_multipart_or_chunked_body():
    async def scenario():
        async def application(scope, receive, send):
            await receive()
        limited = RequestLimits(application)
        assert await request(limited, '/notes/courses/1/ai/ask', multipart=True,
                             headers=[(b'content-length', b'65537')]) == 413
        from starlette.exceptions import HTTPException
        with pytest.raises(HTTPException) as error:
            await request(limited, '/notes/courses/1/ai/ask', multipart=True, body=b'x' * 65537)
        assert error.value.status_code == 413
        assert limited.active == limited.academic == limited.uploads == 0
    asyncio.run(scenario())


def test_upload_lane_stays_bounded_and_is_not_freed_at_response_headers(monkeypatch):
    monkeypatch.setenv('DENTAL_MAX_UPLOADS', '1')
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def application(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200})
            entered.set()
            await release.wait()
            await send({'type': 'http.response.body', 'body': b'complete'})
        limited = RequestLimits(application)
        held = asyncio.create_task(request(limited, '/notes/courses/1/materials', multipart=True))
        await asyncio.wait_for(entered.wait(), 1)
        assert await request(limited, '/notes/courses/2/materials', multipart=True) == 503
        assert limited.uploads == limited.active == 1
        release.set()
        await held
        assert limited.uploads == limited.active == 0
    asyncio.run(scenario())


class CapacityCourse(SQLModel, table=True):
    id: int = Field(primary_key=True)
    owner_user_id: int = Field(index=True)
    title: str = Field(index=True)
    description: str = ''
    updated_at: datetime = Field(index=True)


class CapacityMaterial(SQLModel, table=True):
    id: int = Field(primary_key=True)
    course_id: int = Field(index=True)
    owner_user_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.now)


class CapacityMessage(SQLModel, table=True):
    id: int = Field(primary_key=True)
    course_id: int = Field(index=True)
    owner_user_id: int = Field(index=True)
    content: str


def handler(name, engine, owner=1, path='app/main.py'):
    # Run the real route function with synthetic tables and template output.
    # Authentication/readiness are explicit stubs, not load-tested here.
    tree = ast.parse(Path(path).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    scope = dict(Session=Session, engine=engine, select=select, func=func,
        StudyCourse=CapacityCourse, StudyMaterial=CapacityMaterial, StudyChatMessage=CapacityMessage,
        get_current_user=lambda request: SimpleNamespace(id=owner),
        _owned_study_course=lambda session, user, cid: session.exec(select(CapacityCourse).where(
            CapacityCourse.id == cid, CapacityCourse.owner_user_id == user.id)).first(),
        course_v2_ready=lambda *a, **k: True, study_v2_streaming_enabled=lambda: True,
        templates=SimpleNamespace(TemplateResponse=lambda **kw: kw['context']),
        HTMLResponse=lambda message, status_code: {'status': status_code},
        os=SimpleNamespace(getenv=lambda *a: '0'))
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), path, 'exec'), scope)
    return scope[name]


@pytest.fixture
def owned_data():
    engine = create_engine('sqlite://', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine, tables=[CapacityCourse.__table__, CapacityMaterial.__table__,
                                               CapacityMessage.__table__])
    stamp = datetime(2026, 10, 17)
    with Session(engine) as session:
        session.add_all([CapacityCourse(id=i, owner_user_id=1, title=f'Perio {i}', updated_at=stamp)
                         for i in range(1, 122)])
        session.add(CapacityCourse(id=200, owner_user_id=2, title='Private', updated_at=stamp))
        session.add_all([CapacityMaterial(id=i, course_id=i, owner_user_id=1) for i in range(1, 122)])
        # Corrupt/foreign ownership must not affect the owner's visible counts.
        session.add(CapacityMaterial(id=200, course_id=1, owner_user_id=2))
        session.add_all([CapacityMessage(id=i, course_id=1, owner_user_id=1, content='x' * 1000)
                         for i in range(1, 2001)])
        session.add(CapacityMessage(id=3000, course_id=1, owner_user_id=2, content='PRIVATE'))
        session.commit()
    yield engine
    engine.dispose()


def test_course_list_is_bounded_with_two_queries_and_reachable_older_courses(owned_data):
    engine = owned_data
    statements = []
    event.listen(engine, 'before_cursor_execute', lambda c, cur, sql, *args: statements.append(sql))
    route = handler('study_notes_index', engine)
    first = route(None)
    assert len(first['course_cards']) == 50 and len(statements) == 2
    ids = [card['course'].id for card in first['course_cards']]
    assert ids == list(range(121, 71, -1))
    page = route(None, before=first['next_before'])
    ids += [card['course'].id for card in page['course_cards']]
    last = route(None, before=page['next_before'])
    ids += [card['course'].id for card in last['course_cards']]
    assert len(set(ids)) == 121 and last['next_before'] is None
    assert last['course_cards'][-1]['material_count'] == 1
    assert route(None, before=200)['course_cards'] == []
    assert all('Perio 1' in card['course'].title for card in route(None, q='Perio 1')['course_cards'])


def test_chat_fetches_only_newest_forty_rows_in_chronological_order(owned_data):
    loads = []
    def loaded(target, context):
        loads.append(target.id)
    event.listen(CapacityMessage, 'load', loaded)
    try:
        result = handler('study_ai_page', owned_data)(None, 1, None)
        assert [row.id for row in result['messages']] == list(range(1961, 2001))
        assert len(loads) == 40 and result['material_count'] == 1
    finally:
        event.remove(CapacityMessage, 'load', loaded)


def test_detail_counts_messages_without_loading_their_bodies(owned_data):
    loads = []
    def loaded(target, context):
        loads.append(target.id)
    event.listen(CapacityMessage, 'load', loaded)
    try:
        result = handler('study_course_detail', owned_data)(None, 1)
        assert result['message_count'] == 2000 and loads == []
    finally:
        event.remove(CapacityMessage, 'load', loaded)
