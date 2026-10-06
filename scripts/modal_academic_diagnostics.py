"""Read-only Academic indexing diagnostics; never claim, wake, or publish jobs."""
import json
import os
import modal
from modal_academic_indexer import image as indexing_image
from pathlib import Path

# Modal auto-mounts the entrypoint, not imported root-level modules.
image = indexing_image.add_local_file("modal_academic_indexer.py", "/root/modal_academic_indexer.py")
if Path("baseline_retrieval.py").is_file():
    image = image.add_local_file("baseline_retrieval.py", "/root/baseline_retrieval.py")

app = modal.App("dental-ai-academic-diagnostics")

@app.function(image=image, cpu=1, memory=1024, timeout=120,
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
        from sqlmodel import Session
        from app.study_retrieval_v2 import retrieve_course_context_v2
        from app.dental_knowledge_graph import node_label
        from collections import Counter
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            owner = connection.execute(text("SELECT owner_user_id FROM studycourse WHERE id=3")).scalar_one()
            published = connection.execute(text("""SELECT c.semantic_json FROM studyindexchunk c
                JOIN studymaterial m ON m.id=c.material_id AND m.active_index_version=c.index_version
                WHERE c.course_id=3 AND m.deleted_at IS NULL AND m.index_status='READY'
                AND c.semantic_json IS NOT NULL ORDER BY c.id LIMIT 240""")).scalars().all()
        nodes = Counter(node for value in published for node in json.loads(value).get("nodes", []))
        topics = [node_label(node) for node, _ in nodes.most_common(3)]
        topics = [topic for topic in topics if topic]
        def retrieve(query, history=None, implementation=retrieve_course_context_v2):
            with Session(engine, expire_on_commit=False) as session:
                session.exec(text("SET TRANSACTION READ ONLY"))
                selected = implementation(session, owner_user_id=owner, course_id=3,
                    query=query, recent_history=history or [])
                return {"mode": selected.retrieval_mode, "sufficient": selected.evidence_sufficient,
                    "confidence": selected.evidence_confidence, "chunk_ids": [r.chunk_id for r in selected.evidence],
                    "material_ids": selected.source_material_ids, "resolved_query": selected.resolved_query}
        result["live_retrieval"] = {"course_summary": retrieve("Özetle")}
        if topics:
            history = [{"role":"user", "content":topics[0] + " hakkında bilgi ver"}]
            for name, query in (("topic_summary", "Özetle"), ("detail", "biraz daha detaylı"),
                                ("table", "bunu tablo yap"), ("count", "3 tane say")):
                result["live_retrieval"][name] = retrieve(query, history)
            if len(topics) > 1:
                reference = [{"role":"user", "content":"Ders konularını sırala"},
                    {"role":"assistant", "content":"1. " + topics[0] + "\n2. " + topics[1]}]
                result["live_retrieval"]["ordinal"] = retrieve("ikincisini açıkla", reference)
            if Path("/root/baseline_retrieval.py").is_file():
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("academic_baseline_retrieval", "/root/baseline_retrieval.py")
                baseline = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = baseline
                spec.loader.exec_module(baseline)
                comparisons = []
                queries = [topics[0] + " nedir?", topics[0] + " anatomik ilişkilerini ayrıntılı açıkla"]
                if len(topics) > 1:
                    queries.append(topics[0] + " ve " + topics[1] + " kavramlarını karşılaştır")
                for query in queries:
                    before = retrieve(query, implementation=baseline.retrieve_course_context_v2)
                    after = retrieve(query)
                    comparisons.append({"query":query, "unchanged": before == after, "before":before, "after":after})
                result["long_query_comparisons"] = comparisons
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
