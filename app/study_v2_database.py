"""Runtime capability checks for the PostgreSQL Academic V2 data plane."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlmodel import Session


@dataclass(frozen=True)
class StudyV2DatabaseCapabilities:
    postgres: bool
    fts: bool
    embedding_array: bool
    pgvector: bool


def inspect_capabilities(session: Session) -> StudyV2DatabaseCapabilities:
    if session.get_bind().dialect.name != "postgresql":
        return StudyV2DatabaseCapabilities(False, False, False, False)
    row = session.exec(text(
        "SELECT "
        "to_regprocedure('websearch_to_tsquery(regconfig,text)') IS NOT NULL, "
        "EXISTS (SELECT 1 FROM information_schema.columns "
        "        WHERE table_name='studyindexchunk' AND column_name='embedding_array'), "
        "to_regtype('vector') IS NOT NULL AND "
        "EXISTS (SELECT 1 FROM information_schema.columns "
        "        WHERE table_name='studyindexchunk' AND column_name='embedding_vector')"
    )).one()
    return StudyV2DatabaseCapabilities(True, bool(row[0]), bool(row[1]), bool(row[2]))


def require_worker_capabilities(session: Session) -> StudyV2DatabaseCapabilities:
    caps = inspect_capabilities(session)
    if not caps.postgres:
        raise RuntimeError("Academic V2 deployed worker requires PostgreSQL")
    if not caps.fts or not caps.embedding_array:
        raise RuntimeError("Academic V2 database migration is incomplete")
    sync = session.exec(text("SELECT to_regprocedure('study_v2_sync_pgvector(bigint,text)') IS NOT NULL")).one()
    if not bool(sync[0]):
        raise RuntimeError("Academic V2 pgvector sync helper is missing")
    return caps
