import app.study_v2_service as service


def test_v2_flags_are_fail_closed(monkeypatch):
    for name in (
        "STUDY_ACADEMIC_V2_INDEXING",
        "STUDY_ACADEMIC_V2_READS",
        "STUDY_ACADEMIC_V2_STREAMING",
        "STUDY_ACADEMIC_V2_ONLY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert not service.indexing_enabled()
    assert not service.reads_enabled()
    assert not service.streaming_enabled()
    assert not service.v2_only_enabled()


def test_streaming_cannot_enable_before_v2_reads(monkeypatch):
    monkeypatch.setenv("STUDY_ACADEMIC_V2_STREAMING", "1")
    monkeypatch.setenv("STUDY_ACADEMIC_V2_READS", "0")
    assert not service.streaming_enabled()


def test_v2_only_requires_complete_v2_path(monkeypatch):
    monkeypatch.setenv("STUDY_ACADEMIC_V2_ONLY", "1")
    monkeypatch.setenv("STUDY_ACADEMIC_V2_INDEXING", "0")
    monkeypatch.setenv("STUDY_ACADEMIC_V2_READS", "0")
    try:
        service.validate_configuration()
    except RuntimeError as exc:
        assert "INDEXING" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("V2-only mode accepted disabled indexing")

    monkeypatch.setenv("STUDY_ACADEMIC_V2_INDEXING", "1")
    try:
        service.validate_configuration()
    except RuntimeError as exc:
        assert "READS" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("V2-only mode accepted disabled reads")

    monkeypatch.setenv("STUDY_ACADEMIC_V2_READS", "1")
    service.validate_configuration()
    monkeypatch.setenv("STUDY_V1_SHADOW_INDEXING", "1")
    assert not service.legacy_indexing_required()
