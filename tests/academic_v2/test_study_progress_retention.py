"""Regression tests for persisted Academic AI study progress."""
from pathlib import Path


def test_failed_and_interrupted_runs_do_not_erase_checkpoints():
    source = Path("app/academic_study_runs.py").read_text(encoding="utf-8")
    assert "row.stage='Tamamlanamadı';row.updated_at=now()" in source
    assert "row.status='FAILED';row.error='Çalışma tamamlanamadı. Önceki kayıtların korunuyor.'" in source
    recovery = source.split("def recover(engine):", 1)[1].split("def erase(", 1)[0]
    assert "partial_text=''" not in recovery
    status = source.split("def payload(session,row):", 1)[1]
    assert "row.partial_text=''" not in status.split("if row.status=='DONE':", 1)[0]


def test_checkpoint_does_not_erase_progress_for_hidden_content():
    source = Path("app/academic_study_runs.py").read_text(encoding="utf-8")
    assert "partial=None if hidden else collected" in source
    assert "partial=collected)" in source
    assert "partial[:240000]" in source


def test_long_answer_continuation_remains_bounded():
    source = Path("app/academic_long_answer.py").read_text(encoding="utf-8")
    assert "MAX_CONTINUATIONS = 12" in source
    assert "MAX_ANSWER_CHARS = 1_000_000" in source
    assert "if not allow_continuation or attempt == MAX_CONTINUATIONS:" in source
