#!/usr/bin/env python3
"""Run the release-gating Academic V2 retrieval benchmark on PostgreSQL."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlmodel import Session

from app.study_benchmark import aggregate_scores, load_manifest, score_retrieval
from app.study_retrieval_v2 import retrieve_course_context_v2
from app.study_v2_database import require_worker_capabilities


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", help="80-100 source-annotated dental questions in JSONL")
    parser.add_argument("--output", default="academic_v2_benchmark_result.json")
    args = parser.parse_args()
    questions = load_manifest(args.manifest)
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    engine = create_engine(database_url, pool_size=2, max_overflow=0, pool_pre_ping=True)
    results: list[dict] = []
    with Session(engine, expire_on_commit=False) as session:
        capabilities = require_worker_capabilities(session)
        for item in questions:
            retrieved = retrieve_course_context_v2(
                session,
                owner_user_id=item.owner_user_id,
                course_id=item.course_id,
                query=item.query,
                recent_history=[],
                limit=8,
            )
            score = score_retrieval(item, retrieved.evidence)
            results.append({
                "question_id": item.question_id,
                "query": item.query,
                **score,
                "retrieved": [
                    {"material_id": hit.material_id, "page_start": hit.page_start,
                     "page_end": hit.page_end, "hybrid_score": hit.hybrid_score}
                    for hit in retrieved.evidence
                ],
            })
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "capabilities": capabilities.__dict__,
        "summary": aggregate_scores(results),
        "questions": results,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
