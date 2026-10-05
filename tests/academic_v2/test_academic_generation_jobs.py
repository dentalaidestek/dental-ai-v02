from pathlib import Path

def test_generation_jobs_are_durable_leased_and_deduplicated():
    source = Path("app/academic_generation_jobs.py").read_text(encoding="utf-8")
    assert "class AcademicGenerationJob" in source
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "pg_advisory_xact_lock" in source
    assert "status IN ('QUEUED','RUNNING')" in source
    assert "lease_token" in source
    assert "checkpoint_generation_job" in source

def test_broad_generation_is_not_backgroundtasks_coupled():
    source = Path("app/academic_generation_jobs.py").read_text(encoding="utf-8")
    assert "BackgroundTasks" not in source
