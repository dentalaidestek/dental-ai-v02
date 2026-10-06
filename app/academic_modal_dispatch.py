"""Bounded background wake; PostgreSQL owns indexing and outage recovery."""
import json
import logging
import os
import random
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def wake_academic_modal_indexer() -> bool:
    endpoint = (os.getenv("ACADEMIC_MODAL_DISPATCH_URL") or "").strip()
    secret = (os.getenv("ACADEMIC_MODAL_DISPATCH_SECRET") or "").strip()
    if not endpoint or not secret:
        logger.warning("Academic Modal wake outcome=unconfigured")
        return False
    request = urllib.request.Request(endpoint, data=b"{}", method="POST", headers={
        "Authorization": f"Bearer {secret}", "Content-Type": "application/json",
        "User-Agent": "dental-ai-academic-dispatch/1",
    })
    started = time.monotonic()
    for attempt in range(1, 4):
        status = None
        reason = "network"
        retryable = True
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                status = int(response.status)
                payload = response.read(4097)
            if 200 <= status < 300 and len(payload) <= 4096:
                try:
                    acknowledgement = json.loads(payload)
                except (ValueError, UnicodeError):
                    acknowledgement = None
                if (isinstance(acknowledgement, dict)
                        and acknowledgement.get("ok") is True
                        and acknowledgement.get("scheduled") is True):
                    logger.info("Academic Modal wake outcome=scheduled attempt=%s status=%s elapsed_ms=%s",
                                attempt, status, round((time.monotonic() - started) * 1000))
                    return True
                reason = "invalid_acknowledgement"
            else:
                reason = "http_status"
                retryable = status in {408, 429} or status >= 500
        except urllib.error.HTTPError as exc:
            status = exc.code
            reason = "http_status"
            retryable = status in {408, 429} or status >= 500
            exc.close()
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        logger.warning("Academic Modal wake outcome=failed attempt=%s status=%s reason=%s retry=%s",
                       attempt, status, reason, retryable and attempt < 3)
        if not retryable or attempt == 3:
            return False
        # Full jitter; total retry sleep is bounded by 1.5 seconds.
        time.sleep(random.uniform(0, 0.5 * (2 ** (attempt - 1))))
    return False
