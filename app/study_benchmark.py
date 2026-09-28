"""Evaluation primitives for the 80-100 question Academic V2 gate."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkQuestion:
    question_id: str
    owner_user_id: int
    course_id: int
    query: str
    expected_material_id: int
    expected_pages: tuple[int, ...]
    expected_terms: tuple[str, ...] = ()


def load_manifest(path: str | Path) -> list[BenchmarkQuestion]:
    questions: list[BenchmarkQuestion] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            questions.append(BenchmarkQuestion(
                question_id=str(item["question_id"]),
                owner_user_id=int(item["owner_user_id"]),
                course_id=int(item["course_id"]),
                query=str(item["query"]).strip(),
                expected_material_id=int(item["expected_material_id"]),
                expected_pages=tuple(int(page) for page in item.get("expected_pages", [])),
                expected_terms=tuple(str(term).casefold() for term in item.get("expected_terms", [])),
            ))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid benchmark row {line_number}: {exc}") from exc
    if not 80 <= len(questions) <= 100:
        raise ValueError(f"Academic benchmark must contain 80-100 questions, got {len(questions)}")
    if len({item.question_id for item in questions}) != len(questions):
        raise ValueError("Academic benchmark question_id values must be unique")
    if any(not item.query or not item.expected_pages for item in questions):
        raise ValueError("Every benchmark question needs a query and expected_pages")
    return questions


def score_retrieval(question: BenchmarkQuestion, evidence: list) -> dict:
    material_rank = None
    page_rank = None
    combined = "\n".join(str(item.text) for item in evidence).casefold()
    for rank, item in enumerate(evidence, 1):
        if material_rank is None and int(item.material_id) == question.expected_material_id:
            material_rank = rank
        if (
            page_rank is None
            and int(item.material_id) == question.expected_material_id
            and any(item.page_start <= page <= item.page_end for page in question.expected_pages)
        ):
            page_rank = rank
    term_hits = sum(term in combined for term in question.expected_terms)
    return {
        "material_hit": material_rank is not None,
        "page_hit": page_rank is not None,
        "reciprocal_rank": 1.0 / page_rank if page_rank else 0.0,
        "term_recall": term_hits / len(question.expected_terms) if question.expected_terms else None,
    }


def aggregate_scores(rows: list[dict]) -> dict:
    if not rows:
        return {"count": 0, "material_recall": 0.0, "page_recall": 0.0, "mrr": 0.0, "term_recall": None}
    term_rows = [row["term_recall"] for row in rows if row.get("term_recall") is not None]
    return {
        "count": len(rows),
        "material_recall": sum(bool(row["material_hit"]) for row in rows) / len(rows),
        "page_recall": sum(bool(row["page_hit"]) for row in rows) / len(rows),
        "mrr": sum(float(row["reciprocal_rank"]) for row in rows) / len(rows),
        "term_recall": sum(term_rows) / len(term_rows) if term_rows else None,
    }
