from sqlalchemy import create_engine
from sqlmodel import Session

from app.study_v2_database import inspect_capabilities


def test_sqlite_is_never_mistaken_for_production_capability():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        caps = inspect_capabilities(session)
    assert not caps.postgres
    assert not caps.fts
    assert not caps.embedding_array
    assert not caps.pgvector
