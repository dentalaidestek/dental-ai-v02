from app import study_colocated_worker as worker


def test_colocated_worker_is_fail_closed(monkeypatch):
    monkeypatch.delenv("STUDY_ACADEMIC_V2_INDEXING", raising=False)
    monkeypatch.delenv("STUDY_ACADEMIC_V2_COLOCATED_WORKER", raising=False)
    assert not worker.colocated_worker_enabled()


def test_colocated_worker_requires_indexing(monkeypatch):
    monkeypatch.setenv("STUDY_ACADEMIC_V2_COLOCATED_WORKER", "1")
    monkeypatch.setenv("STUDY_ACADEMIC_V2_INDEXING", "0")
    assert not worker.colocated_worker_enabled()
    monkeypatch.setenv("STUDY_ACADEMIC_V2_INDEXING", "1")
    assert worker.colocated_worker_enabled()


def test_worker_environment_is_low_footprint_and_overrideable():
    environment = worker.build_worker_environment({})
    assert environment["STUDY_V2_RESOURCE_CLASS"] == "MIXED"
    assert environment["STUDY_V2_DB_POOL_SIZE"] == "1"
    assert environment["STUDY_V2_PARSE_BATCH_PAGES"] == "4"

    overridden = worker.build_worker_environment({"STUDY_V2_DB_POOL_SIZE": "2"})
    assert overridden["STUDY_V2_DB_POOL_SIZE"] == "2"
