import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError
from app.database_pool import ObservedQueuePool


def test_pool_reports_holders_without_query_data_and_preserves_bound(caplog):
    engine = create_engine('sqlite://', poolclass=ObservedQueuePool,
                           pool_size=2, max_overflow=0, pool_timeout=0.01)
    engine.pool.diagnostic_role = 'web'
    with engine.connect() as first, engine.connect():
        first.exec_driver_sql("SELECT 'private-patient-value'")
        with caplog.at_level(logging.WARNING), pytest.raises(TimeoutError):
            engine.connect()
        assert engine.pool.checkedout() == 2
        assert 'db.pool_exhausted role=web' in caplog.text
        assert 'age_seconds' in caplog.text
        assert 'private-patient-value' not in caplog.text
        assert 'SELECT' not in caplog.text
        with pytest.raises(TimeoutError):
            engine.connect()
        assert len(caplog.records) == 1
    assert not engine.pool._holders
    with engine.connect():
        assert engine.pool.checkedout() == 1
    engine.dispose()
