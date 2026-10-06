"""Read-only Academic indexing diagnostics; never claim, wake, or publish jobs."""
import json
import os
import modal

app = modal.App("dental-ai-academic-diagnostics")
image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "SQLAlchemy==2.0.54", "psycopg2-binary==2.9.13",
)

@app.function(image=image, cpu=0.25, memory=256, timeout=60,
              max_containers=1,
              secrets=[modal.Secret.from_name("dental-ai-academic-indexer")])
def snapshot():
    from sqlalchemy import create_engine, text
    from urllib.parse import urlsplit
    url = (os.getenv("DATABASE_URL") or "").strip().replace("postgres://", "postgresql://", 1)
    if not url:
        return {"error": "DATABASE_URL_missing"}
    hostname = urlsplit(url).hostname or ""
    result = {"db_host_kind": "render_internal" if hostname.endswith(".internal") or hostname.startswith("dpg-") and "." not in hostname else "external"}
    engine = create_engine(url, pool_size=1, max_overflow=0,
                           connect_args={"connect_timeout": 5, "application_name": "academic-readonly-diagnostics"})
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            def rows(sql):
                return [dict(row) for row in connection.execute(text(sql)).mappings()]
            result["queue"] = rows("SELECT status, stage, resource_class, count(*) AS jobs FROM studyindexjob GROUP BY status, stage, resource_class ORDER BY status, stage, resource_class")
            result["eligible"] = rows("""SELECT resource_class, count(*) AS jobs FROM studyindexjob
                WHERE (status='QUEUED' AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP))
                   OR (status='RUNNING' AND lease_until IS NOT NULL AND lease_until <= CURRENT_TIMESTAMP)
                GROUP BY resource_class""")
            result["recent_jobs"] = rows("""SELECT id, course_id, material_id, status, stage, resource_class, attempts,
                failure_attempts, worker_id, lease_until, next_retry_at, expected_page_count,
                started_at, completed_at, updated_at,
                (last_error IS NOT NULL) AS has_error
                FROM studyindexjob ORDER BY id DESC LIMIT 30""")
            result["pages"] = rows("SELECT course_id, status, extraction_method, count(*) AS pages FROM studyindexpage GROUP BY course_id, status, extraction_method")
            result["chunks"] = rows("SELECT course_id, count(*) AS chunks, count(semantic_json) AS semantic_chunks FROM studyindexchunk GROUP BY course_id")
            result["material_schema"] = rows("SELECT column_name FROM information_schema.columns WHERE table_name='studymaterial' ORDER BY ordinal_position")
            result["course_schema"] = rows("SELECT column_name FROM information_schema.columns WHERE table_name='studycourse' ORDER BY ordinal_position")
            connection.rollback()
    except Exception as exc:
        # Exception strings can contain connection URLs: never print them.
        result["error_type"] = type(exc).__name__
        original = getattr(exc, "orig", None)
        result["sqlstate"] = getattr(original, "pgcode", None)
    finally:
        engine.dispose()
    return result

@app.local_entrypoint()
def main():
    print("ACADEMIC_READONLY_SNAPSHOT " + json.dumps(snapshot.remote(), default=str, sort_keys=True))
