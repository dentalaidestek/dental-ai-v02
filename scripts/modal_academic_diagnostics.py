"""Read-only Academic indexing diagnostics; never claim, wake, or publish jobs."""
import json
import os
import modal
from modal_academic_indexer import image

app = modal.App("dental-ai-academic-diagnostics")

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
    from app.study_local_ocr import _TESSDATA_PATH, _DENTAL_WORDS_PATH
    import tesserocr
    result["ocr_assets"] = {"tur": (_TESSDATA_PATH / "tur.traineddata").is_file(),
                            "eng": (_TESSDATA_PATH / "eng.traineddata").is_file(),
                            "dental_words": _DENTAL_WORDS_PATH.is_file()}
    try:
        with tesserocr.PyTessBaseAPI(path=str(_TESSDATA_PATH) + "/", lang="tur+eng"):
            result["ocr_init"] = True
    except Exception as exc:
        result["ocr_init"] = False
        result["ocr_init_error_type"] = type(exc).__name__
    engine = create_engine(url, pool_size=1, max_overflow=0,
                           connect_args={"connect_timeout": 5, "application_name": "academic-readonly-diagnostics"})
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            def rows(sql):
                return [dict(row) for row in connection.execute(text(sql)).mappings()]
            result["queue"] = rows("SELECT status, stage, resource_class, count(*) AS jobs FROM studyindexjob GROUP BY status, stage, resource_class ORDER BY status, stage, resource_class")
            import re
            result["failed_errors"] = [{"id": row["id"], "error_code": (
                row["last_error"] if re.fullmatch(r"[A-Z][A-Z0-9_:]{2,100}", row["last_error"] or "") else "NON_CODE_ERROR_REDACTED"
            )} for row in rows("SELECT id, last_error FROM studyindexjob WHERE status='FAILED' ORDER BY id")]
            result["materials"] = rows("""SELECT m.id, m.course_id, m.index_status,
                m.deleted_at IS NOT NULL AS deleted, m.active_index_version IS NOT NULL AS has_active,
                m.building_index_version IS NOT NULL AS has_building,
                j.status AS job_status, j.index_version = m.active_index_version AS published_generation_matches,
                j.index_version = m.building_index_version AS building_generation_matches
                FROM studymaterial m LEFT JOIN studyindexjob j ON j.material_id=m.id
                WHERE m.course_id=3 ORDER BY m.id""")
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
