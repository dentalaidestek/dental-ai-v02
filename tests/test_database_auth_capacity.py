"""Exercise actual authentication with a real bounded pool and parallel requests."""
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlmodel import Field, SQLModel, Session, create_engine, select
from app import database
from app.database_pool import ObservedQueuePool


class PoolAuthUser(SQLModel, table=True):
    id: int = Field(primary_key=True)
    role: str = 'DOCTOR'
    email: str | None = None
    is_active: bool = True
    email_verified_at: datetime | None = None


class PoolAuthToken(SQLModel, table=True):
    id: int = Field(primary_key=True)
    token_hash: str
    user_id: int
    expires_at: datetime


class PoolAdminVerifiedSession(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)
    user_id: int


@pytest.fixture
def auth(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'auth.db'),
        poolclass=ObservedQueuePool, pool_size=4, max_overflow=0, pool_timeout=1,
        connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine, tables=[PoolAuthUser.__table__, PoolAuthToken.__table__, PoolAdminVerifiedSession.__table__])
    with Session(engine) as session:
        session.add(PoolAuthUser(id=1, email_verified_at=datetime.now()))
        session.add(PoolAuthToken(id=1, user_id=1, token_hash='hashed', expires_at=datetime.now()+timedelta(days=1)))
        session.commit()
    module = ast.parse((Path(__file__).parents[1] / 'app/main.py').read_text())
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'get_current_user')
    code = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), function], type_ignores=[])
    namespace = dict(Session=Session, engine=engine, select=select, User=PoolAuthUser,
        SessionToken=PoolAuthToken, SESSION_COOKIE='session', hash_session_token=lambda t: 'hashed',
        AdminVerifiedSession=PoolAdminVerifiedSession,
        _utcnow_naive=datetime.now)
    exec(compile(ast.fix_missing_locations(code), '<actual-authentication>', 'exec'), namespace)
    yield engine, namespace['get_current_user']
    engine.dispose()


def request():
    return SimpleNamespace(state=SimpleNamespace(), cookies={'session':'raw-token'})


def test_auth_reads_token_and_user_in_one_query_releases_connection_and_caches_only_request(auth):
    engine, current = auth
    statements = []
    event.listen(engine, 'before_cursor_execute', lambda c, cu, st, p, co, many: statements.append(st))
    first = request()
    assert current(first).id == 1
    assert current(first).id == 1
    assert len(statements) == 1
    assert engine.pool.checkedout() == 0
    with Session(engine) as session:
        user = session.get(PoolAuthUser, 1)
        user.is_active = False
        session.add(user)
        session.commit()
    assert current(request()) is None
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize('condition', ['expired', 'unverified', 'inactive', 'orphan', 'unknown'])
def test_single_query_auth_preserves_rejections_and_expired_cleanup(auth, condition):
    engine, current = auth
    with Session(engine) as session:
        user = session.get(PoolAuthUser, 1)
        token = session.get(PoolAuthToken, 1)
        if condition == 'expired': token.expires_at = datetime.now()-timedelta(seconds=1)
        elif condition == 'unverified': user.email_verified_at = None
        elif condition == 'inactive': user.is_active = False
        elif condition == 'orphan': token.user_id = 999
        elif condition == 'unknown': token.token_hash = 'different'
        session.add(user); session.add(token); session.commit()
    assert current(request()) is None
    assert engine.pool.checkedout() == 0
    if condition == 'expired':
        with Session(engine) as session:
            assert session.get(PoolAuthToken, 1) is None


def test_twenty_parallel_actual_auth_requests_release_all_four_connections(auth):
    engine, current = auth
    with ThreadPoolExecutor(max_workers=12) as executor:
        assert list(executor.map(lambda _: current(request()).id, range(20))) == [1]*20
    assert engine.pool.checkedout() == 0
    assert engine.pool.size() == 4
    assert engine.pool.overflow() == 0
    assert not engine.pool._holders


@pytest.mark.parametrize('email,mfa,allowed',[
    ('dentalaidestek@gmail.com',False,False),
    ('other@example.test',True,False),
    ('dentalaidestek@gmail.com',True,True),
])
def test_admin_auth_requires_fixed_identity_and_mfa_without_retaining_connections(auth,email,mfa,allowed):
    engine,current=auth
    with Session(engine) as session:
        user=session.get(PoolAuthUser,1);user.role='ADMIN';user.email=email;session.add(user)
        if mfa:session.add(PoolAdminVerifiedSession(token_hash='hashed',user_id=1))
        session.commit()
    assert bool(current(request())) is allowed
    assert engine.pool.checkedout()==0


@pytest.mark.parametrize('role,size', [('web',4), ('router',2)])
def test_role_capacity_stays_bounded_and_does_not_grow_router_pool(monkeypatch, role, size):
    monkeypatch.delenv('DENTAL_' + role.upper() + '_DB_POOL_SIZE', raising=False)
    seen = {}
    def create(url, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(pool=SimpleNamespace())
    monkeypatch.setattr(database, 'create_engine', create)
    result = database.create_app_engine('postgresql://localhost/test', role=role)
    assert seen['pool_size'] == size
    assert seen['max_overflow'] == 0
    assert seen['pool_timeout'] == 5
    assert result.pool.diagnostic_role == role

