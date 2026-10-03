from app.academic_coverage import build_coverage_plan
from app.academic_generation import plan_generation_batches, dedupe_generated_questions

def row(cid, section):
    return (cid, 1, "note.pdf", 1, 1, section, "TEXT", "", None, None, None, None, 1.0, cid, None)

def test_generation_batches_are_bounded_and_preserve_total_budget():
    plan = build_coverage_plan([row(i, "Endodonti") for i in range(1, 21)], 25)
    batches = plan_generation_batches(plan, max_questions_per_batch=8, max_chunks_per_batch=12)
    assert sum(x.question_count for x in batches) == 25
    assert all(x.question_count <= 8 for x in batches)
    assert all(len(x.chunk_ids) <= 12 for x in batches)

def test_generation_batches_span_coverage_buckets():
    plan = build_coverage_plan([row(1, "Endo"), row(2, "Perio"), row(3, "Radyoloji")], 12)
    batches = plan_generation_batches(plan)
    assert {x.section_title for x in batches} == {"Endo", "Perio", "Radyoloji"}

def test_generated_question_dedupe_rejects_close_paraphrase_shape():
    questions = [
        "ANB açısının normal değeri kaçtır?",
        "ANB açısının normal değeri 2 derece midir?",
        "SNA açısı neyi değerlendirir?",
    ]
    kept = dedupe_generated_questions(questions)
    assert len(kept) == 2
    assert kept[-1].startswith("SNA")


def test_resume_skips_completed_bucket_work():
    from app.academic_coverage import bucket_key
    plan = build_coverage_plan([row(i, "Endo") for i in range(1, 5)] + [row(10, "Perio")], 10)
    first = plan.buckets[0]
    batches = plan_generation_batches(plan, generated_by_bucket={bucket_key(first): first.question_budget})
    assert all(x.bucket_key != bucket_key(first) for x in batches)

def test_resume_only_plans_remaining_questions():
    from app.academic_coverage import bucket_key
    plan = build_coverage_plan([row(i, "Endo") for i in range(1, 6)], 10)
    bucket = plan.buckets[0]
    batches = plan_generation_batches(plan, generated_by_bucket={bucket_key(bucket): 7})
    assert sum(x.question_count for x in batches) == 3


def test_hydration_windows_dedupe_chunks_and_stay_bounded():
    from app.academic_generation import hydration_windows, GenerationBatch
    batches = (
        GenerationBatch("a", 1, "A", (), (1, 2, 3), 3),
        GenerationBatch("b", 1, "B", (), (3, 4, 5), 3),
        GenerationBatch("c", 1, "C", (), (6, 7), 2),
    )
    windows = hydration_windows(batches, max_unique_chunks=5)
    assert windows[0] == (1, 2, 3, 4, 5)
    assert windows[1] == (6, 7)
    assert all(len(x) <= 5 for x in windows)
