from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine

from app.auth_rate import admit, bucket_key, clear


def test_two_instances_atomically_share_limit(tmp_path):
    url = 'sqlite:///' + str(tmp_path / 'shared.db')
    engines = [create_engine(url, connect_args={'check_same_thread': False, 'timeout': 20}) for _ in range(2)]
    SQLModel.metadata.create_all(engines[0])
    def attempt(i):
        try:
            admit(engines[i % 2], 'login', 'Doctor@Example.test', limit=8, window=600)
            return 200
        except HTTPException as exc:
            assert exc.headers['Retry-After']
            return exc.status_code
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(attempt, range(24)))
        assert statuses.count(200) == 8
        assert statuses.count(429) == 16
        with engines[0].connect() as conn:
            row = conn.execute(text('SELECT * FROM authratebucket')).one()
            assert row.attempts == 24
            assert 'doctor' not in row.bucket_key.lower()
        clear(engines[1], bucket_key('login', ' doctor@example.test '))
        admit(engines[0], 'login', 'Doctor@Example.test', limit=8, window=600)
    finally:
        for engine in engines:
            engine.dispose()


def test_expired_window_resets_and_store_failure_does_not_disable_protection(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'limits.db'))
    SQLModel.metadata.create_all(engine)
    key = admit(engine, 'login', 'user', limit=1, window=600)
    with pytest.raises(HTTPException) as blocked:
        admit(engine, 'login', 'user', limit=1, window=600)
    assert blocked.value.status_code == 429
    with engine.begin() as conn:
        conn.execute(text('UPDATE authratebucket SET reset_at=0 WHERE bucket_key=:key'), {'key': key})
    admit(engine, 'login', 'user', limit=1, window=600)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE authratebucket'))
    with pytest.raises(HTTPException) as unavailable:
        admit(engine, 'login', 'user', limit=1, window=600)
    assert unavailable.value.status_code == 503
    assert 'authratebucket' not in unavailable.value.detail
    engine.dispose()


def test_revision_nine_migration_is_repeatable_and_preserves_existing_identity(tmp_path, monkeypatch):
    from app import main, migrate
    from sqlmodel import Session
    engine = create_engine('sqlite:///' + str(tmp_path / 'release.db'))
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username='migration-synthetic', display_name='Synthetic', role='DOCTOR', password_hash='preserved-hash')
        session.add(user)
        session.commit()
        user_id = user.id
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE authratebucket'))
        conn.execute(text('CREATE TABLE dental_schema_revision(id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        conn.execute(text('INSERT INTO dental_schema_revision VALUES(1,8)'))
    monkeypatch.setattr(main, 'engine', engine)
    migrate.apply()
    migrate.apply()
    migrate.require_schema(engine)
    admit(engine, 'login', 'migration-synthetic', limit=8, window=600)
    with Session(engine) as session:
        user = session.get(main.User, user_id)
        assert user.username == 'migration-synthetic'
        assert user.password_hash == 'preserved-hash'
    engine.dispose()
