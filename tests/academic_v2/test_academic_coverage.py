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


def test_coverage_ledger_tracks_only_bucket_budget():
    from app.academic_coverage import build_coverage_ledger, bucket_key
    plan = build_coverage_plan([
        row(1, 1, "Endodonti", ("pulpitis",)),
        row(2, 1, "Periodontoloji", ("probing_depth",)),
    ], 10)
    first = plan.buckets[0]
    ledger = build_coverage_ledger(plan, {bucket_key(first): first.question_budget + 50})
    assert ledger.generated_questions == first.question_budget
    assert ledger.remaining_questions == 10 - first.question_budget
    assert bucket_key(first) in ledger.completed_bucket_keys

def test_retrieval_coverage_scan_is_metadata_only_and_hydration_is_owner_scoped():
    from pathlib import Path
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert "def _coverage_metadata_page" in source
    assert "'' AS text_content" in source
    assert "def _coverage_evidence_rows" in source
    assert "c.owner_user_id=:owner AND c.course_id=:course" in source
    assert "c.id = ANY(CAST(:chunk_ids AS BIGINT[]))" in source


def test_coverage_builder_uses_keyset_pagination_and_version_cache():
    from pathlib import Path
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert "c.id > :after_id" in source
    assert "OFFSET" not in source[source.index("def _coverage_metadata_page"):source.index("def _coverage_evidence_rows")]
    assert "cached_coverage_plan(owner_user_id, course_id, fingerprint, requested_count)" in source
    assert "active_index_version" in source[source.index("def _course_index_fingerprint"):source.index("def get_or_build_coverage_plan")]


def test_streaming_accumulator_is_bounded_but_preserves_true_weight():
    from app.academic_coverage import CoverageAccumulator
    rows = []
    for cid in range(1, 1001):
        rows.append((cid, 7, "large.pdf", cid, cid, "Endodonti", "TEXT", "",
                     None, None, None, None, 1.0, cid, '{"nodes":["pulpitis"]}'))
    acc = CoverageAccumulator(representative_limit=12)
    for start in range(0, len(rows), 37):
        acc.add_rows(rows[start:start + 37])
    plan = acc.build(40)
    assert plan.scanned_rows == 1000
    assert len(plan.buckets) == 1
    assert plan.buckets[0].weight == 1000
    assert len(plan.buckets[0].chunk_ids) <= 12
    assert len(plan.covered_chunk_ids) <= 12


def test_streaming_representatives_are_stable_across_page_sizes():
    from app.academic_coverage import CoverageAccumulator
    rows = [
        (cid, 8, "large.pdf", cid, cid, "Cerrahi", "TEXT", "",
         None, None, None, None, 1.0, cid, '{"nodes":["dry_socket"]}')
        for cid in range(1, 401)
    ]
    a = CoverageAccumulator(representative_limit=16)
    b = CoverageAccumulator(representative_limit=16)
    for start in range(0, 400, 31):
        a.add_rows(rows[start:start + 31])
    for start in range(0, 400, 97):
        b.add_rows(rows[start:start + 97])
    assert a.build(20).covered_chunk_ids == b.build(20).covered_chunk_ids
