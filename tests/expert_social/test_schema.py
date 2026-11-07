import pytest
from sqlalchemy import text, inspect
from sqlmodel import create_engine
from app import main
from app.expert_social_schema import apply, require_schema
from app.expert_social_models import SOCIAL_MODELS


def test_schema_idempotent_and_readiness_rejects_missing_table(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "migration.db"))
    main.User.__table__.create(engine)
    with pytest.raises(RuntimeError):
        require_schema(engine)
    apply(engine)
    apply(engine)
    require_schema(engine)
    assert all(inspect(engine).has_table(m.__tablename__) for m in SOCIAL_MODELS)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE socialcomment"))
    with pytest.raises(RuntimeError):
        require_schema(engine)


def test_social_revision_one_upgrades_to_two_without_losing_posts(tmp_path):
    from app.expert_social_models import SocialFollow, SocialPost

    engine = create_engine("sqlite:///" + str(tmp_path / "upgrade.db"))
    main.User.__table__.create(engine)
    apply(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE dental_social_revision SET version=1"))
        SocialFollow.__table__.drop(conn)
    with pytest.raises(RuntimeError):
        require_schema(engine)
    apply(engine)
    require_schema(engine)
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT version FROM dental_social_revision")).scalar()
            == 2
        )
    assert inspect(engine).has_table(SocialPost.__tablename__)
