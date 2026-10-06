"""Authenticate one real HTTP wake only after proving the durable queue empty."""
import json
import os
import modal
from modal_academic_indexer import image as indexing_image

app = modal.App("dental-ai-academic-dispatch-smoke")
image = indexing_image.add_local_file("modal_academic_indexer.py", "/root/modal_academic_indexer.py")

@app.function(image=image, cpu=0.25, memory=256, timeout=30, max_containers=1,
              secrets=[modal.Secret.from_name("dental-ai-academic-indexer")])
def smoke():
    from sqlalchemy import text
    from app.study_index_worker_main import build_worker_engine
    from app.academic_modal_dispatch import wake_academic_modal_indexer
    engine = build_worker_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            pending = connection.execute(text("""SELECT count(*) FROM studyindexjob
                WHERE status IN ('QUEUED', 'RUNNING')""")).scalar_one()
        if pending:
            return {"skipped": True, "pending_jobs": pending, "acknowledged": False}
        os.environ["ACADEMIC_MODAL_DISPATCH_URL"] = "https://dentalaidestek--dental-ai-academic-indexer-dispatch.modal.run"
        return {"pending_jobs": 0, "acknowledged": wake_academic_modal_indexer()}
    finally:
        engine.dispose()

@app.local_entrypoint()
def main():
    result = smoke.remote()
    print("ACADEMIC_AUTHENTICATED_WAKE " + json.dumps(result, sort_keys=True))
    if not result.get("acknowledged"):
        raise SystemExit(1)
