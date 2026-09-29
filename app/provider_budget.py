"""Shared request budgets and expiring provider slots, without open I/O transactions."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
import threading
from sqlalchemy import delete, text, update
from sqlmodel import Field, Session, SQLModel, select


class ProviderCounter(SQLModel, table=True):
    key: str = Field(primary_key=True)
    requests: int = 0
    expires_at: datetime = Field(index=True)


class ProviderSlot(SQLModel, table=True):
    token: str = Field(primary_key=True)
    scope: str = Field(index=True)
    expires_at: datetime = Field(index=True)


class ProviderBusy(RuntimeError):
    pass

_local_lock = threading.Lock()
_schema_lock = threading.Lock()
_ready_engines = set()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _engine():
    from app.study_router_state import _ENGINE
    if _ENGINE not in _ready_engines:
        with _schema_lock:
            if _ENGINE not in _ready_engines:
                if os.getenv('RENDER'):
                    from app.migrate import require_schema
                    require_schema(_ENGINE)
                else:
                    SQLModel.metadata.create_all(_ENGINE, tables=[ProviderCounter.__table__, ProviderSlot.__table__])
                _ready_engines.add(_ENGINE)
    return _ENGINE


def _limits(provider, model):
    from app.study_router_state import _request_budget
    configured = _request_budget(provider, model)
    now = _now()
    windows = {'day': (now.strftime('%Y-%m-%d'), now + timedelta(days=2)),
               'month': (now.strftime('%Y-%m'), now + timedelta(days=62))}
    for period, (window, expiry) in windows.items():
        limit = configured.get(period, 0)
        if limit:
            yield f'{provider}:{model}:{period}:{window}', int(limit), expiry


@contextmanager
def reservation(provider, model, *, capacity=None, account_scope=None):
    engine = _engine()
    scope = account_scope or provider
    maximum = capacity or int(os.getenv('DENTAL_PROVIDER_MAX_INFLIGHT', '4'))
    if maximum < 1:
        raise ProviderBusy('Provider capacity is disabled')
    token = secrets.token_hex(24)
    stamp = _now()
    limits = list(_limits(provider, model))
    # Wildcard account budgets must count all models together.
    import json
    raw = json.loads(os.getenv('STUDY_ROUTER_REQUEST_BUDGETS_JSON', '{}') or '{}')
    if f'{provider}:{model}' not in raw and (f'{provider}:*' in raw or provider in raw):
        limits = [(key.replace(f'{provider}:{model}:', f'{provider}:*:', 1), limit, expiry) for key, limit, expiry in limits]
    with _local_lock, Session(engine) as session:
        if engine.dialect.name == 'postgresql':
            lock_key = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], 'big', signed=True)
            session.exec(text('SELECT pg_advisory_xact_lock(:key)'), params={'key': lock_key})
        session.exec(delete(ProviderSlot).where(ProviderSlot.expires_at <= stamp))
        session.exec(delete(ProviderCounter).where(ProviderCounter.expires_at <= stamp))
        active = session.exec(select(ProviderSlot.token).where(ProviderSlot.scope == scope)).all()
        if len(active) >= maximum:
            raise ProviderBusy('Provider capacity is occupied; retry later')
        for key, limit, expiry in limits:
            row = session.get(ProviderCounter, key)
            if row is None:
                row = ProviderCounter(key=key, expires_at=expiry)
            if row.requests >= limit:
                raise ProviderBusy('Configured request budget exhausted')
            row.requests += 1
            session.add(row)
        session.add(ProviderSlot(token=token, scope=scope, expires_at=stamp + timedelta(minutes=3)))
        session.commit()
    stop, lost = threading.Event(), threading.Event()
    def renew():
        while not stop.wait(30):
            try:
                with engine.begin() as connection:
                    result = connection.execute(update(ProviderSlot).where(
                        ProviderSlot.token == token, ProviderSlot.expires_at > _now(),
                    ).values(expires_at=_now() + timedelta(minutes=3)))
                    if result.rowcount != 1:
                        lost.set()
                        return
            except Exception:
                lost.set()
                return
    thread = threading.Thread(target=renew, daemon=True, name='dental-provider-lease')
    thread.start()
    try:
        yield
        if lost.is_set():
            raise ProviderBusy('Provider reservation lost')
    finally:
        stop.set()
        thread.join(6)
        with engine.begin() as connection:
            connection.execute(delete(ProviderSlot).where(ProviderSlot.token == token))
