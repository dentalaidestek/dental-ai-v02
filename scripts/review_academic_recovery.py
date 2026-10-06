"""Group private recovery records into patterns for resolver fixes and tests.

Read-only. Does not promote Gemini hypotheses into runtime rules. Requires an
authorized DB connection and explicit owner/course; output contains user text.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path


def summarize(rows):
    groups = defaultdict(lambda: {"count": 0, "outcomes": Counter(), "examples": []})
    for row in rows:
        details = json.loads(row["details_json"])
        key = (row["error_class"], details.get("initial_mode", "unknown"),
               tuple(sorted(details.get("missing_facets", []))))
        group = groups[key]
        group["count"] += 1
        group["outcomes"][row["outcome"]] += 1
        if len(group["examples"]) < 5:
            group["examples"].append({"event_id": row["id"], "query": details.get("query"),
                "plan": details.get("plan"), "review_status": row["review_status"]})
    return [{"error_class": key[0], "retrieval_mode": key[1], "missing_facets": key[2], **group}
            for key, group in sorted(groups.items(), key=lambda pair: -pair[1]["count"])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-user-id", type=int, required=True)
    parser.add_argument("--course-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from sqlalchemy import create_engine, text
    database_url = os.environ["DATABASE_URL"]
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT id, error_class, outcome, review_status, details_json
            FROM academicrecoveryevent
            WHERE owner_user_id=:owner AND course_id=:course
            ORDER BY id DESC LIMIT :limit
        """), {"owner": args.owner_user_id, "course": args.course_id,
               "limit": min(10000, max(1, args.limit))}).mappings().all()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"records": len(rows), "patterns": summarize(rows)},
                                     ensure_ascii=False, indent=2))
    print(f"Reviewed {len(rows)} records; wrote private pattern report to {args.output}")


if __name__ == "__main__":
    main()
