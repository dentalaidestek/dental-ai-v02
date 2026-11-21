"""Regression contracts for durable Academic AI runs and bounded continuation."""
from pathlib import Path


def test_failed_and_interrupted_runs_preserve_visible_checkpoints():
    source = Path("app/academic_study_runs.py").read_text(encoding="utf-8")
    drain = source.split("def _drain(engine):", 1)[1].split("def wake(engine):", 1)[0]
    recovery = source.split("def recover(engine):", 1)[1].split("def cancel_run(", 1)[0]
    status = source.split("def payload(session,row):", 1)[1].split("if row.status=='DONE':", 1)[0]
    assert "row.stage='Tamamlanamadı';row.updated_at=now()" in drain
    assert "row.partial_text=''" not in drain
    assert "partial_text=''" not in recovery
    assert "row.partial_text=''" not in status
    assert "partial[:240000]" in source


def test_hidden_payload_keeps_last_safe_checkpoint_and_flushes_final_visible_chunk():
    source = Path("app/academic_study_runs.py").read_text(encoding="utf-8")
    generation = source.split("def generation(", 1)[1].split("def _drain(", 1)[0]
    assert "partial=None if hidden else collected" in generation
    assert "checkpoint(engine,run_id,stage='Yanıt hazırlanıyor',partial=collected)" in generation
    assert "or len(collected)>12000" not in generation


def test_single_run_cancellation_is_owner_and_course_scoped():
    source = Path("app/academic_study_runs.py").read_text(encoding="utf-8")
    cancel = source.split("def cancel_run(", 1)[1].split("def erase(", 1)[0]
    assert "StudyRun.id==run_id" in cancel
    assert "StudyRun.owner_user_id==owner" in cancel
    assert "StudyRun.course_id==course" in cancel
    assert "('QUEUED','RUNNING','INTERRUPTED')" in cancel
    assert "row.status='CANCELLED'" in cancel
    assert "row.partial_text=''" in cancel


def test_long_answer_continuation_is_larger_but_still_bounded():
    source = Path("app/academic_long_answer.py").read_text(encoding="utf-8")
    assert "MAX_ANSWER_CHARS = 240_000" in source
    assert "MAX_CONTINUATIONS = 6" in source
    assert "max(32768, options['max_output_tokens'])" in source
    assert "budget=max(32768,budget)" in source


def test_anthropic_large_tasks_get_budget_without_inflating_ordinary_turns():
    source = Path("app/study_ai_v2.py").read_text(encoding="utf-8")
    assert "output_budget = 32768" in source
    assert "else 7000" in source
    assert "allow_continuation=True" in source
