"""One-shot recovery of the four verified Ortoo failures; no wake or new generation."""
import json
import time
import modal
from modal_academic_indexer import image as indexing_image

image = indexing_image.add_local_file("modal_academic_indexer.py", "/root/modal_academic_indexer.py")
app = modal.App("dental-ai-academic-ortoo-recovery")
JOB_IDS = (17, 20, 21, 22)
EXPECTED_ERROR = "signal only works in main thread of the main interpreter"

@app.function(image=image, cpu=0.25, memory=256, timeout=30, max_containers=1,
              secrets=[modal.Secret.from_name("dental-ai-academic-indexer")])
def recover():
    from sqlalchemy import text
    from app.study_index_worker_main import build_worker_engine
    engine = build_worker_engine()
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout='10s'"))
            found = connection.execute(text("""
                SELECT j.id, j.status, j.stage, j.last_error, j.index_version,
                       j.lease_until, m.building_index_version, m.active_index_version,
                       m.deleted_at,
                       (SELECT count(*) FROM studyindexpage p WHERE p.material_id=j.material_id AND p.index_version=j.index_version) AS pages
                FROM studyindexjob j JOIN studymaterial m ON m.id=j.material_id
                WHERE j.course_id=3 AND j.id IN (17,20,21,22)
                FOR UPDATE OF j, m
            """)).mappings().all()
            if len(found) != 4:
                raise RuntimeError("RECOVERY_TARGET_MISMATCH")
            if all(r["status"] == "DONE" and r["active_index_version"] == r["index_version"] for r in found):
                return {"already_done": True, "job_ids": list(JOB_IDS)}
            if not all(r["status"] == "FAILED" and r["stage"] == "OCR"
                       and r["last_error"] == EXPECTED_ERROR and r["lease_until"] is None
                       and r["deleted_at"] is None and r["pages"] > 0
                       and r["building_index_version"] == r["index_version"]
                       and r["active_index_version"] is None for r in found):
                raise RuntimeError("RECOVERY_GUARD_REJECTED")
            changed = connection.execute(text("""
                UPDATE studyindexjob SET status='QUEUED', failure_attempts=0,
                       next_retry_at=CURRENT_TIMESTAMP, last_error=NULL,
                       updated_at=CURRENT_TIMESTAMP
                WHERE id IN (17,20,21,22) AND course_id=3 AND status='FAILED'
                      AND stage='OCR' AND lease_until IS NULL AND last_error=:error
            """), {"error": EXPECTED_ERROR}).rowcount
            if changed != 4:
                raise RuntimeError("RECOVERY_CAS_REJECTED")
            return {"requeued": changed, "job_ids": list(JOB_IDS),
                    "generations_preserved": True, "checkpoints_preserved": sum(r["pages"] for r in found),
                    "wake_sent": False}
    finally:
        engine.dispose()

@app.function(image=image, cpu=0.25, memory=256, timeout=30, max_containers=1,
              secrets=[modal.Secret.from_name("dental-ai-academic-indexer")])
def progress():
    from sqlalchemy import text
    from app.study_index_worker_main import build_worker_engine
    engine = build_worker_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            rows = connection.execute(text("""
                SELECT j.id, j.status, j.stage, j.attempts, j.worker_id,
                    j.lease_until, m.index_status,
                    j.index_version=m.active_index_version AS published_matches,
                    (SELECT count(*) FROM studyindexpage p WHERE p.material_id=j.material_id AND p.index_version=j.index_version AND p.status='OCR_DONE') AS ocr_done,
                    (SELECT count(*) FROM studyindexpage p WHERE p.material_id=j.material_id AND p.index_version=j.index_version AND p.status='OCR_REQUIRED') AS ocr_pending,
                    (SELECT count(*) FROM studyindexchunk c WHERE c.material_id=j.material_id AND c.index_version=j.index_version) AS chunks
                FROM studyindexjob j JOIN studymaterial m ON m.id=j.material_id
                WHERE j.course_id=3 AND j.id IN (17,20,21,22) ORDER BY j.id
            """)).mappings().all()
            return [dict(r) for r in rows]
    finally:
        engine.dispose()

@app.local_entrypoint()
def main():
    print("ORTOO_RECOVERY " + json.dumps(recover.remote(), default=str, sort_keys=True), flush=True)
    # No HTTP dispatch and no drainer spawn: deployed watchdog must rescue the queue.
    deadline = time.monotonic() + 600
    previous = None
    while time.monotonic() < deadline:
        current = progress.remote()
        encoded = json.dumps(current, default=str, sort_keys=True)
        if encoded != previous:
            print("ORTOO_PROGRESS " + encoded, flush=True)
            previous = encoded
        if len(current) == 4 and all(r["status"] == "DONE" and r["index_status"] == "READY" and r["published_matches"] for r in current):
            print("ORTOO_E2E_PUBLISHED_READY", flush=True)
            return
        if any(r["status"] == "FAILED" for r in current):
            raise RuntimeError("ORTOO_RECOVERY_FAILED")
        time.sleep(3)
    raise RuntimeError("ORTOO_E2E_TIMED_OUT")
