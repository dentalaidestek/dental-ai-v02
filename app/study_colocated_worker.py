"""Lifecycle supervisor for the no-extra-service Academic V2 worker.

The indexer still runs in a separate OS process with its own database pool; it
only shares the existing Render container so the free deployment does not need
an additional background-worker service.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Mapping

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def colocated_worker_enabled() -> bool:
    return _flag("STUDY_ACADEMIC_V2_INDEXING") and _flag(
        "STUDY_ACADEMIC_V2_COLOCATED_WORKER"
    )


def build_worker_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Use conservative slice sizes on the shared free instance."""
    environment = dict(source if source is not None else os.environ)
    defaults = {
        "STUDY_V2_RESOURCE_CLASS": "MIXED",
        "STUDY_V2_DB_POOL_SIZE": "1",
        "STUDY_V2_PARSE_BATCH_PAGES": "4",
        "STUDY_V2_CHUNK_BATCH_PAGES": "4",
        "STUDY_V2_EMBED_BATCH_CHUNKS": "4",
        "STUDY_V2_OCR_BATCH_PAGES": "1",
        "STUDY_V2_IDLE_SLEEP_SECONDS": "2",
    }
    for name, value in defaults.items():
        environment.setdefault(name, value)
    return environment


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=25)
    except asyncio.TimeoutError:
        logger.warning("Academic V2 colocated worker did not stop; killing it")
        process.kill()
        await process.wait()


async def supervise_colocated_worker() -> None:
    """Keep one isolated index process alive for the lifetime of the web app."""
    restart_delay = 3
    process: asyncio.subprocess.Process | None = None
    try:
        while True:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.study_index_worker_main",
                env=build_worker_environment(),
            )
            logger.info("Academic V2 colocated worker started pid=%s", process.pid)
            return_code = await process.wait()
            logger.error(
                "Academic V2 colocated worker exited code=%s; restarting in %ss",
                return_code,
                restart_delay,
            )
            process = None
            await asyncio.sleep(restart_delay)
            restart_delay = min(restart_delay * 2, 60)
    except asyncio.CancelledError:
        if process is not None:
            await _stop_process(process)
        raise


def start_colocated_worker_task() -> asyncio.Task | None:
    if not colocated_worker_enabled():
        logger.info("Academic V2 colocated worker disabled")
        return None
    return asyncio.create_task(
        supervise_colocated_worker(), name="academic-v2-colocated-worker"
    )

