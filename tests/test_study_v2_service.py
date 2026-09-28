import app.study_v2_service as service


def test_v2_flags_are_fail_closed(monkeypatch):
    for name in ("STUDY_ACADEMIC_V2_INDEXING", "STUDY_ACADEMIC_V2_READS", "STUDY_ACADEMIC_V2_STREAMING"):
        monkeypatch.delenv(name, raising=False)
    assert not service.indexing_enabled()
    assert not service.reads_enabled()
    assert not service.streaming_enabled()


def test_streaming_cannot_enable_before_v2_reads(monkeypatch):
    monkeypatch.setenv("STUDY_ACADEMIC_V2_STREAMING", "1")
    monkeypatch.setenv("STUDY_ACADEMIC_V2_READS", "0")
    assert not service.streaming_enabled()
