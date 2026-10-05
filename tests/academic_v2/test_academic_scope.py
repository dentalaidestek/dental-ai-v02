"""Behavior checks for zero-provider Dental Academic scope routing."""
from app.dental_academic_scope import classify_academic_question_scope

assert classify_academic_question_scope("ANB açısı kaç derecedir?") == "DENTAL"
assert classify_academic_question_scope("48 numaralı diş mandibular kanala yakın mı?") == "DENTAL"
assert classify_academic_question_scope("bu notu özetle") == "STUDY_ACTION"
assert classify_academic_question_scope(
    "bunu biraz daha açıkla",
    recent_history=[{"role": "assistant", "content": "ANB açısı..."}],
) == "FOLLOWUP"
assert classify_academic_question_scope("programlama algoritması anlat") == "NON_DENTAL"
assert classify_academic_question_scope("ceza hukuku nedir?") == "NON_DENTAL"

# Unseen biomedical/dental vocabulary must not be falsely rejected. Retrieval
# evidence is the second gate for UNKNOWN.
assert classify_academic_question_scope("pterygomandibular raphe nerede?") == "UNKNOWN"
assert classify_academic_question_scope("Nance holding arch endikasyonu") == "UNKNOWN"

print("Dental Academic scope routing: OK")


def test_scope_accepts_previous_student_question_matrix():
    """Run the prior 100+ Academic V2 student-question matrix through scope only."""
    import importlib.util
    from pathlib import Path
    benchmark_path = Path(__file__).with_name("test_adversarial_benchmark.py")
    spec = importlib.util.spec_from_file_location("_scope_question_matrix", benchmark_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    questions = []
    questions.extend(query for query, *_ in module.BASE)
    questions.extend(query for query, *_ in module.MULTI)
    questions.extend(query for query, *_ in module.QUALIFIERS)
    questions.extend(module.NEGATIVE)
    questions.extend(module.NON_NEGATIVE)
    questions.extend(module.VISUAL_TRUE)
    questions.extend(module.VISUAL_FALSE)
    questions.extend(query for query, *_ in module.TYPOS)
    questions.extend(query for query, *_ in module.COMPLEX_EXAM_QUERIES)
    questions.extend(query for query, *_ in module.WORKFLOW_PRESSURE_CASES)
    questions.extend(query for query, *_ in module.STUDENT_NOTE_REQUEST_CENSUS)

    # Scope is only the first gate: valid dental/study questions may be DENTAL,
    # STUDY_ACTION, FOLLOWUP or UNKNOWN. UNKNOWN is intentionally retrieval-gated.
    allowed = {"DENTAL", "STUDY_ACTION", "FOLLOWUP", "UNKNOWN"}
    rejected = []
    for query in questions:
        scope = classify_academic_question_scope(query)
        if scope not in allowed:
            rejected.append((query, scope))

    assert len(questions) >= 100
    assert not rejected, rejected
