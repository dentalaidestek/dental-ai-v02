"""Read-only Academic indexing diagnostics; never claim, wake, or publish jobs."""
import json
import os
import modal
from modal_academic_indexer import image as indexing_image

# Modal auto-mounts the entrypoint, not imported root-level modules.
image = indexing_image.add_local_file("modal_academic_indexer.py", "/root/modal_academic_indexer.py")

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
    if result["ocr_init"]:
        from concurrent.futures import ThreadPoolExecutor
        from PIL import Image, ImageDraw, ImageFont
        from app.study_local_ocr import _recognize
        def recognize_probe(_):
            # Synthetic image tests real threaded native OCR without PDFs or DB writes.
            with Image.new("L", (700, 120), 255) as probe:
                ImageDraw.Draw(probe).text((20, 30), "DENTAL TEST 123", fill=0,
                    font=ImageFont.load_default(size=42))
                value, confidence = _recognize(probe, psm=tesserocr.PSM.SINGLE_BLOCK, timeout_ms=5000)
                return {"recognized": "DENTAL" in value.upper(), "confidence": confidence}
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                result["parallel_ocr_probe"] = list(pool.map(recognize_probe, range(4)))
        except Exception as exc:
            result["parallel_ocr_error_type"] = type(exc).__name__
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
                row["last_error"] if re.fullmatch(r"[A-Z][A-Za-z0-9_:]{2,100}", row["last_error"] or "") else "NON_CODE_ERROR_REDACTED"
            )} for row in rows("SELECT id, last_error FROM studyindexjob WHERE status='FAILED' ORDER BY id")]
            error_signatures = {
                "tessdata_init": "invalid tessdata path",
                "tesseract_init": "Failed to init API",
                "detached_orm": "not bound to a Session",
                "missing_module": "No module named",
                "render_argument": "unexpected keyword argument",
                "ocr_engine": "OCR_ENGINE_FAILED",
                "ocr_render": "OCR_RENDER_FAILED",
                "ocr_timeout": "OCR_RECOGNITION_TIMEOUT",
                "missing_source": "SOURCE_MISSING",
            }
            result["failed_error_signatures"] = [{"id": row["id"], "signatures": [
                key for key, marker in error_signatures.items() if marker in (row["last_error"] or "")
            ]} for row in rows("SELECT id, last_error FROM studyindexjob WHERE status='FAILED' ORDER BY id")]
            def safe_error_detail(message):
                detail = str(message or "")
                for name, value in os.environ.items():
                    if len(value) >= 6 and any(marker in name for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD", "DATABASE_URL")):
                        detail = detail.replace(value, "[REDACTED]")
                detail = re.sub(r"(?:https?|postgres(?:ql)?|r2)://[^\s]+", "[URL_REDACTED]", detail)
                detail = re.sub(r"\b[A-Za-z0-9/_+=-]{24,}\b", "[TOKEN_REDACTED]", detail)
                return detail[:400]
            result["failed_error_details_safe"] = [{"id": row["id"], "detail": safe_error_detail(row["last_error"])}
                for row in rows("SELECT id, last_error FROM studyindexjob WHERE status='FAILED' ORDER BY id")]
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
            source_rows = rows("SELECT id, file_path, size_bytes FROM studymaterial WHERE course_id=3 AND deleted_at IS NULL ORDER BY id")
            connection.rollback()
        from app.object_storage import _client, _object_key, _settings, enabled
        result["r2_enabled"] = enabled()
        result["source_access"] = []
        if enabled():
            bucket = _settings()[0]
            for source in source_rows:
                try:
                    client = _client()
                    key = _object_key(source["file_path"])
                    metadata = client.head_object(Bucket=bucket, Key=key)
                    response = client.get_object(Bucket=bucket, Key=key, Range="bytes=0-63")
                    try:
                        header = response["Body"].read(64)
                    finally:
                        response["Body"].close()
                    result["source_access"].append({"material_id": source["id"], "exists": True,
                        "size_matches": metadata["ContentLength"] == source["size_bytes"],
                        "pdf_header": header.startswith(b"%PDF-")})
                except Exception as exc:
                    result["source_access"].append({"material_id": source["id"], "error_type": type(exc).__name__})
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
