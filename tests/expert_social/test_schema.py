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


def test_upgrade_existing_social_tables_creates_queue_and_expiry_indexes(tmp_path):
    expected = {
        "socialpost": "ix_socialpost_moderation",
        "socialcomment": "ix_socialcomment_moderation",
        "publication": "ix_publication_moderation",
        "doimatch": "ix_doimatch_created_at",
    }
    engine = create_engine("sqlite:///" + str(tmp_path / "indexes.db"))
    main.User.__table__.create(engine)
    apply(engine)
    for table, name in expected.items():
        assert name in {index["name"] for index in inspect(engine).get_indexes(table)}
    # The revision number alone must not mask a partially missing index.
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_socialpost_moderation"))
    with pytest.raises(RuntimeError):
        require_schema(engine)
    apply(engine)
    require_schema(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE dental_social_revision SET version=2"))
        for name in expected.values():
            connection.execute(text(f"DROP INDEX {name}"))
    with pytest.raises(RuntimeError):
        require_schema(engine)
    apply(engine)
    require_schema(engine)
    for table, name in expected.items():
        assert name in {index["name"] for index in inspect(engine).get_indexes(table)}


def test_additive_indexes_preserve_the_deployed_revision_two_contract(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "compatible.db"))
    main.User.__table__.create(engine)
    apply(engine)
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT version FROM dental_social_revision WHERE id=1")
            ).scalar_one()
            == 2
        )
