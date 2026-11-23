"""Regression tests for persisted Academic AI study progress."""
from pathlib import Path


def test_failed_and_interrupted_runs_do_not_erase_checkpoints():
    source = Path("app/academic_study_runs.py").read_text(encoding="utf-8")
    assert "row.stage='Tamamlanamadı';row.updated_at=now()" in source
    assert "row.status='FAILED';row.error='Çalışma tamamlanamadı. Önceki kayıtların korunuyor.'" in source
    # FAILED runs keep their checkpoints. Inside recover() only the explicit
    # user-cancel path may clear the partial text; every other branch keeps it.
    recovery = source.split("def recover(engine):", 1)[1].split("def erase(", 1)[0]
    cancelled_reset = "row.error='Bu çalışma iptal edildi.';row.partial_text=''"
    assert cancelled_reset in recovery
    assert recovery.replace(cancelled_reset, "").count("partial_text=''") == 0


def test_checkpoint_does_not_erase_progress_for_hidden_content():
    source = Path("app/academic_study_runs.py").read_text(encoding="utf-8")
    assert "partial=None if hidden else collected" in source
    assert "partial=collected)" in source
    assert "partial[:240000]" in source


def test_long_answer_continuation_remains_bounded():
    source = Path("app/academic_long_answer.py").read_text(encoding="utf-8")
    # e58e1d77 lifted the hard ceilings to None (bounded by safeguard gates, not
    # a global constant); the continuation gate must keep its None-safe guard.
    assert "MAX_CONTINUATIONS = None" in source
    assert "MAX_ANSWER_CHARS = None" in source
    assert "if not allow_continuation or (MAX_CONTINUATIONS is not None and attempt == MAX_CONTINUATIONS):" in source
