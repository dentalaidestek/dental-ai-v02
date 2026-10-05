"""Modal entrypoint for Academic AI V2 durable indexing.

This deliberately reuses the production StudyIndexJob/lease/checkpoint/publish
contract. Modal supplies elastic compute; PostgreSQL remains authoritative.
No web process is imported and no second queue is introduced.

Deploy with:
    modal deploy modal_academic_indexer.py

Required Modal secrets/environment:
    DATABASE_URL
    R2_ENABLED=1
    R2_BUCKET_NAME
    R2_ENDPOINT_URL
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
and the STUDY_ACADEMIC_V2_* feature flags used by production.

The function scales to zero when idle because min_containers is left at zero.
"""
from __future__ import annotations

import os
import modal

app = modal.App("dental-ai-academic-indexer")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install(
        "sqlmodel==0.0.44",
        "SQLAlchemy==2.0.54",
        "psycopg2-binary==2.9.13",
        "pypdf==6.19.0",
        "Pillow==12.3.0",
        "pypdfium2==5.13.0",
        "tesserocr==2.11.0",
        "boto3>=1.35,<2",
    )
    .add_local_python_source("app")
)

# Start conservatively. Modal may run several independent durable jobs in
# parallel, while each invocation still obeys the existing DB lease fencing.
MAX_SLICES_PER_INVOCATION = int(os.getenv("STUDY_MODAL_MAX_SLICES", "256"))


@app.function(
    image=image,
    cpu=4.0,
    memory=8192,
    timeout=60 * 30,
    min_containers=0,
    max_containers=8,
    scaledown_window=20,
    secrets=[modal.Secret.from_name("dental-ai-academic-indexer")],
)
def drain_index_queue() -> dict[str, int | str]:
    # Larger bounded slices are safe off the shared Render web instance.
    os.environ.setdefault("STUDY_V2_RESOURCE_CLASS", "MIXED")
    os.environ.setdefault("STUDY_V2_DB_POOL_SIZE", "1")
    os.environ.setdefault("STUDY_V2_PARSE_BATCH_PAGES", "50")
    os.environ.setdefault("STUDY_V2_CHUNK_BATCH_PAGES", "32")
    os.environ.setdefault("STUDY_V2_OCR_BATCH_PAGES", "16")
    os.environ.setdefault("STUDY_V2_OCR_PARALLELISM", "4")
    os.environ.setdefault("STUDY_V2_LEASE_SECONDS", "600")
    os.environ.setdefault("STUDY_V2_IDLE_SLEEP_SECONDS", "1")

    from sqlmodel import Session
    from app.study_index_worker_main import build_worker_engine
    from app.study_index_worker import run_one_slice
    from app.study_v2_database import require_worker_capabilities

    engine = build_worker_engine()
    processed = 0
    published = 0
    last = "IDLE"
    try:
        with Session(engine, expire_on_commit=False) as session:
            require_worker_capabilities(session)

        # One invocation drains useful work and exits immediately when the
        # durable queue is empty. Modal can therefore scale back to zero.
        for _ in range(max(1, MAX_SLICES_PER_INVOCATION)):
            did_work = False
            for resource_class in ("NORMAL", "OCR_HEAVY"):
                with Session(engine, expire_on_commit=False) as session:
                    result = run_one_slice(session, resource_class=resource_class)
                last = result
                if result != "IDLE":
                    did_work = True
                    processed += 1
                    if result == "PUBLISHED":
                        published += 1
            if not did_work:
                break
        return {"processed_slices": processed, "published": published, "last": last}
    finally:
        engine.dispose()


@app.function(
    image=image,
    cpu=1.0,
    memory=512,
    timeout=60,
    min_containers=0,
    max_containers=2,
    scaledown_window=10,
    secrets=[modal.Secret.from_name("dental-ai-academic-indexer")],
)
def kick() -> str:
    """Cheap trigger: fan out bounded drainers; DB leases prevent double work."""
    for _ in range(4):
        drain_index_queue.spawn()
    return "scheduled"
