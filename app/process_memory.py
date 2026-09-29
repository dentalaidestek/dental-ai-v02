"""Best-effort heap release and safe worker recycling at job boundaries."""
from __future__ import annotations

import ctypes
import gc
import logging
import os
from pathlib import Path
import resource
import sys
from collections.abc import Callable

logger = logging.getLogger(__name__)


def current_rss_bytes() -> int:
    """Return current resident bytes on Linux, with a conservative fallback."""
    try:
        fields = Path("/proc/self/statm").read_text().split()
        return int(fields[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        maximum = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Linux reports KiB; macOS reports bytes.
        return maximum * 1024 if sys.platform.startswith("linux") else maximum


def release_unused_memory() -> int:
    """Collect Python cycles and ask glibc to return free arenas to the OS."""
    collected = gc.collect()
    try:
        libc = ctypes.CDLL(None)
        malloc_trim = getattr(libc, "malloc_trim")
        malloc_trim.argtypes = [ctypes.c_size_t]
        malloc_trim.restype = ctypes.c_int
        malloc_trim(0)
    except (AttributeError, OSError):
        # Non-glibc platforms still benefit from Python cycle collection.
        pass
    return collected


def configured_rss_limit_bytes(name: str) -> int:
    raw = (os.getenv(name) or "0").strip()
    try:
        megabytes = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer number of MiB") from exc
    if megabytes < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return megabytes * 1024 * 1024


def recycle_if_over_limit(
    env_name: str,
    *,
    module_name: str,
    cleanup: Callable[[], None] | None = None,
) -> bool:
    """Re-exec a durable worker only between slices, never during owned work."""
    release_unused_memory()
    limit = configured_rss_limit_bytes(env_name)
    if not limit:
        return False
    rss = current_rss_bytes()
    if rss < limit:
        return False
    logger.warning(
        "worker.recycle module=%s rss_bytes=%s limit_bytes=%s",
        module_name,
        rss,
        limit,
    )
    if cleanup is not None:
        cleanup()
    os.execv(sys.executable, [sys.executable, "-m", module_name])
    return True
