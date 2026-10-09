"""Atomic authentication admission shared by every instance through PostgreSQL."""
import hashlib
import math
import os

# One policy for web/native/admin. Preserve the stricter legacy configuration
# when either client was previously configured differently.
LOGIN_WINDOW_SECONDS = max(60, int(os.getenv("AUTH_LOGIN_RATE_WINDOW_SECONDS", str(max(int(os.getenv("WEB_LOGIN_RATE_WINDOW_SECONDS", "600")), int(os.getenv("MOBILE_LOGIN_RATE_WINDOW_SECONDS", "600")))))))
LOGIN_MAX_FAILURES = max(3, int(os.getenv("AUTH_LOGIN_RATE_MAX_FAILURES", str(min(int(os.getenv("WEB_LOGIN_RATE_MAX_FAILURES", "8")), int(os.getenv("MOBILE_LOGIN_RATE_MAX_FAILURES", "8")))))))

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Field, SQLModel


class AuthRateBucket(SQLModel, table=True):
    bucket_key: str = Field(primary_key=True)
    attempts: int
    reset_at: int = Field(index=True)


def bucket_key(scope: str, identity: str) -> str:
    return scope + ':' + hashlib.sha256(identity.strip().casefold().encode()).hexdigest()


def admit(engine, scope: str, identity: str, *, limit: int, window: int) -> str:
    key = bucket_key(scope, identity)
    if limit < 1 or window < 1:
        raise ValueError('Invalid authentication rate configuration')
    clock = "CAST(EXTRACT(EPOCH FROM clock_timestamp()) AS BIGINT)" if engine.dialect.name == 'postgresql' else "CAST(strftime('%s','now') AS INTEGER)"
    try:
        with engine.begin() as connection:
            now = int(connection.execute(text('SELECT ' + clock)).scalar_one())
            row = connection.execute(text('''
                INSERT INTO authratebucket(bucket_key, attempts, reset_at)
                VALUES (:key, 1, :reset)
                ON CONFLICT(bucket_key) DO UPDATE SET
                    attempts = CASE WHEN authratebucket.reset_at <= :now THEN 1
                                    ELSE authratebucket.attempts + 1 END,
                    reset_at = CASE WHEN authratebucket.reset_at <= :now THEN :reset
                                    ELSE authratebucket.reset_at END
                RETURNING attempts, reset_at
            '''), {'key': key, 'reset': now + window, 'now': now}).one()
            # Bounded opportunistic cleanup: no extra scheduler or paid service.
            connection.execute(text('''DELETE FROM authratebucket WHERE bucket_key IN
                (SELECT bucket_key FROM authratebucket WHERE reset_at < :old
                 ORDER BY reset_at LIMIT 100)'''), {'old': now - 86400})
    except SQLAlchemyError as exc:
        # Do not disable protection if the shared store is unavailable.
        raise HTTPException(503, 'Giriş kontrolü geçici olarak kullanılamıyor.', headers={'Retry-After': '5'}) from exc
    if row.attempts > limit:
        raise HTTPException(429, 'Çok fazla giriş denemesi. Daha sonra tekrar deneyin.', headers={'Retry-After': str(max(1, math.ceil(row.reset_at - now)))})
    return key


def clear(engine, key: str) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM authratebucket WHERE bucket_key=:key'), {'key': key})
    except SQLAlchemyError:
        # Success is already authenticated; retaining the throttle is safer than
        # failing a valid session solely because counter cleanup was unavailable.
        pass
