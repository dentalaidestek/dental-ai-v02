import json
from dataclasses import dataclass

import pytest

from app.study_benchmark import BenchmarkQuestion, aggregate_scores, load_manifest, score_retrieval


@dataclass
class _Hit:
    material_id: int
    page_start: int
    page_end: int
    text: str


def test_manifest_refuses_small_cherry_picked_sets(tmp_path):
    path = tmp_path / "small.jsonl"
    path.write_text(json.dumps({
        "question_id": "q1", "owner_user_id": 1, "course_id": 2,
        "query": "Soru", "expected_material_id": 3, "expected_pages": [4],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="80-100"):
        load_manifest(path)


def test_page_level_scoring_and_aggregation():
    question = BenchmarkQuestion("q", 1, 2, "Soru", 9, (7,), ("pulpa", "nekroz"))
    score = score_retrieval(question, [
        _Hit(8, 1, 1, "distractor"),
        _Hit(9, 7, 7, "Pulpa nekroz bulgusu"),
    ])
    assert score == {"material_hit": True, "page_hit": True, "reciprocal_rank": 0.5, "term_recall": 1.0}
    summary = aggregate_scores([score])
    assert summary["page_recall"] == 1.0 and summary["mrr"] == 0.5
