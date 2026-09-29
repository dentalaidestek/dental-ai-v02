import pytest

from app import process_memory


def test_recycle_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TEST_RECYCLE_RSS_MB", raising=False)
    monkeypatch.setattr(process_memory, "release_unused_memory", lambda: 0)
    monkeypatch.setattr(process_memory, "current_rss_bytes", lambda: 10**12)
    monkeypatch.setattr(process_memory.os, "execv", lambda *args: pytest.fail("unexpected exec"))
    assert not process_memory.recycle_if_over_limit(
        "TEST_RECYCLE_RSS_MB", module_name="app.fake_worker"
    )


def test_recycle_cleans_up_and_reexecs_only_above_limit(monkeypatch):
    monkeypatch.setenv("TEST_RECYCLE_RSS_MB", "128")
    monkeypatch.setattr(process_memory, "release_unused_memory", lambda: 0)
    monkeypatch.setattr(process_memory, "current_rss_bytes", lambda: 129 * 1024 * 1024)
    calls = []
    monkeypatch.setattr(process_memory.os, "execv", lambda executable, args: calls.append((executable, args)))
    assert process_memory.recycle_if_over_limit(
        "TEST_RECYCLE_RSS_MB",
        module_name="app.fake_worker",
        cleanup=lambda: calls.append("cleanup"),
    )
    assert calls[0] == "cleanup"
    assert calls[1][1][-2:] == ["-m", "app.fake_worker"]


@pytest.mark.parametrize("value", ["-1", "many"])
def test_recycle_limit_rejects_invalid_configuration(monkeypatch, value):
    monkeypatch.setenv("TEST_RECYCLE_RSS_MB", value)
    with pytest.raises(RuntimeError):
        process_memory.configured_rss_limit_bytes("TEST_RECYCLE_RSS_MB")


def test_academic_worker_sigterm_requests_drain(monkeypatch):
    from app import study_index_worker_main as worker

    monkeypatch.setattr(worker, "_stop", False)
    worker._handle_stop(None, None)
    assert worker._stop is True


def test_application_worker_sigterm_stops_before_next_claim(monkeypatch):
    from app import main as app_main
    from app import migrate
    from app import work_worker as worker

    class Engine:
        disposed = False

        def dispose(self):
            self.disposed = True

    engine = Engine()
    handlers = {}
    claims = []
    monkeypatch.setattr(app_main, "engine", engine)
    monkeypatch.setattr(migrate, "require_schema", lambda candidate: None)
    monkeypatch.setattr(worker.signal, "signal", lambda signum, handler: handlers.setdefault(signum, handler))
    monkeypatch.setattr(worker, "recycle_if_over_limit", lambda *args, **kwargs: False)

    def run_one(candidate):
        claims.append(candidate)
        handlers[worker.signal.SIGTERM](None, None)
        return True

    monkeypatch.setattr(worker, "run_one", run_one)
    worker.main()
    assert claims == [engine]
    assert engine.disposed
