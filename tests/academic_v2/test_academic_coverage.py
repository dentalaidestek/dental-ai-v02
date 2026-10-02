from app.academic_coverage import build_coverage_plan

def row(cid, mid, section, nodes=(), kind="TEXT"):
    import json
    meta = json.dumps({"nodes": list(nodes)})
    return (cid, mid, "note.pdf", 1, 1, section, kind, "evidence", None, None, None, None, 1.0, cid, meta)

def test_coverage_budget_matches_requested_count_and_spans_sections():
    rows = [
        row(1, 1, "Endodonti", ("pulpitis",)),
        row(2, 1, "Endodonti", ("pulpitis",)),
        row(3, 1, "Endodonti", ("working_length",)),
        row(4, 1, "Periodontoloji", ("probing_depth",)),
        row(5, 1, "Radyoloji", ("cbct",)),
    ]
    plan = build_coverage_plan(rows, 20)
    assert sum(b.question_budget for b in plan.buckets) == 20
    assert {b.section_title for b in plan.buckets} == {"Endodonti", "Periodontoloji", "Radyoloji"}

def test_question_chunks_do_not_define_factual_coverage():
    rows = [
        row(1, 1, "Endodonti", ("pulpitis",), "QUESTION"),
        row(2, 1, "Periodontoloji", ("probing_depth",)),
    ]
    plan = build_coverage_plan(rows, 10)
    assert all(b.section_title != "Endodonti" for b in plan.buckets)
    assert sum(b.question_budget for b in plan.buckets) == 10

def test_large_requested_count_is_bounded():
    plan = build_coverage_plan([row(1, 1, "A", ("x",))], 999)
    assert plan.requested_count == 200
    assert sum(b.question_budget for b in plan.buckets) == 200
