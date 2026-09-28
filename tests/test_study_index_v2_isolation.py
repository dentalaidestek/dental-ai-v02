from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
JOBS = (ROOT / "app" / "study_index_jobs.py").read_text(encoding="utf-8")
WORKER = (ROOT / "app" / "study_index_worker.py").read_text(encoding="utf-8")
RAG = (ROOT / "app" / "study_rag.py").read_text(encoding="utf-8")
NOTES_AI = (ROOT / "app" / "templates" / "notes_ai.html").read_text(encoding="utf-8")


def test_v2_worker_is_not_wired_into_live_v1_yet():
    # Worker processes remain isolated from web workers. V2 reads are protected
    # by a default-off flag and never run_one_slice inside a request.
    assert "from app.study_index_worker import" not in MAIN
    assert "run_one_slice(" not in MAIN
    assert "study_v2_reads_enabled()" in MAIN


def test_live_v1_rag_does_not_read_building_v2_chunks():
    assert "StudyIndexChunk" not in RAG
    assert "studyindexchunk" not in RAG.lower()


def test_v2_streaming_is_feature_gated_end_to_end():
    assert "study_v2_streaming_enabled()" in MAIN
    assert "if not study_v2_streaming_enabled()" in MAIN
    assert "const v2Streaming" in NOTES_AI
    assert "if (!v2Streaming)" in NOTES_AI


def test_publish_requires_current_generation_and_live_lease():
    assert "building_index_version" in JOBS
    assert "lease_until > :now" in JOBS
    assert "deleted_at" in JOBS


def test_worker_uses_durable_artifacts_not_cursor_checkpoint():
    assert "missing_page_numbers(" in WORKER
    assert "pending_embedding_chunks(" in WORKER
    assert "cursor" not in WORKER.lower()
