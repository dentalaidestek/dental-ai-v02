#!/usr/bin/env python3
"""Read-only EXPLAIN ANALYZE report for Program's PostgreSQL hot paths.

Use only with a disposable or staging database. The script requires both
DENTAL_TEST_DATABASE_URL and DENTAL_ALLOW_PROGRAM_PLAN_REPORT=1. It selects
only synthetic owner-scoped row IDs inside EXPLAIN; it never prints row data.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text


def _plan_summary(raw):
    if isinstance(raw, str):
        raw = json.loads(raw)
    root = raw[0]["Plan"] if isinstance(raw, list) else raw["Plan"]
    indexes = set()
    pending = [root]
    while pending:
        node = pending.pop()
        if node.get("Index Name"):
            indexes.add(node["Index Name"])
        pending.extend(node.get("Plans") or [])
    return {
        "execution_ms": root.get("Actual Total Time"),
        "rows": root.get("Actual Rows"),
        "shared_hit_blocks": root.get("Shared Hit Blocks", 0),
        "shared_read_blocks": root.get("Shared Read Blocks", 0),
        "indexes": sorted(indexes),
        "plan_node": root.get("Node Type"),
    }


def main():
    database_url = os.environ.get("DENTAL_TEST_DATABASE_URL")
    if not database_url:
        raise SystemExit("DENTAL_TEST_DATABASE_URL is required; production DATABASE_URL is not read.")
    if os.environ.get("DENTAL_ALLOW_PROGRAM_PLAN_REPORT") != "1":
        raise SystemExit("Set DENTAL_ALLOW_PROGRAM_PLAN_REPORT=1 to confirm a disposable/staging target.")
    owner_id = int(os.environ.get("DENTAL_PROGRAM_BENCHMARK_OWNER_ID", "1"))
    engine = create_engine(database_url, pool_size=1, max_overflow=0, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        raise SystemExit("Program query plan report requires PostgreSQL.")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    queries = (
        (
            "schedule_range",
            """
            SELECT id FROM scheduleevent
            WHERE owner_user_id=:owner
              AND status <> 'DELETED'
              AND start_at <= :range_end
              AND (recurrence_rule='WEEKLY' OR start_at >= :range_start OR end_at >= :range_start)
              AND (recurrence_rule <> 'WEEKLY' OR recurrence_until IS NULL
                   OR recurrence_until='' OR recurrence_until >= :range_date)
            ORDER BY start_at LIMIT 50
            """,
            {
                "owner": owner_id,
                "range_start": now - timedelta(days=1),
                "range_end": now + timedelta(days=30),
                "range_date": now.date().isoformat(),
            },
        ),
        (
            "schedule_snapshot_change",
            """
            SELECT id FROM scheduleevent
            WHERE owner_user_id=:owner
              AND (created_at > :snapshot OR updated_at > :snapshot)
            LIMIT 1
            """,
            {"owner": owner_id, "snapshot": now - timedelta(minutes=15)},
        ),
        (
            "reminder_due_batch",
            """
            SELECT id FROM programreminderjob
            WHERE status='PENDING' AND run_at <= :now
            ORDER BY run_at LIMIT 100
            """,
            {"now": now},
        ),
    )

    try:
        reports = []
        for name, statement, params in queries:
            with engine.connect() as connection:
                with connection.begin():
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    raw = connection.execute(
                        text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement),
                        params,
                    ).scalar_one()
            reports.append({"query": name, **_plan_summary(raw)})
        print(json.dumps({"database": "postgresql", "owner_scope": "one synthetic account", "reports": reports}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
