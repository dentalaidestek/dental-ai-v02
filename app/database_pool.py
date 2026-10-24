"""Bounded pool diagnostics: code locations only, never SQL, values or locals."""
import logging
import sys
import threading
import time

from sqlalchemy import event
from sqlalchemy.exc import TimeoutError
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)


def _locations(frame):
    locations = []
    while frame is not None:
        filename = frame.f_code.co_filename.replace("\\", "/")
        if "/app/" in filename and not filename.endswith("/database_pool.py"):
            locations.append(f"app/{filename.rsplit('/app/', 1)[1]}:{frame.f_code.co_name}:{frame.f_lineno}")
        frame = frame.f_back
    return locations[:10]


class ObservedQueuePool(QueuePool):
    def __init__(self, *args, **kwargs):
        self._holders = {}
        self._holders_lock = threading.Lock()
        self._last_report = float('-inf')
        self.diagnostic_role = 'unknown'
        super().__init__(*args, **kwargs)
        event.listen(self, 'checkout', self._remember)
        event.listen(self, 'checkin', self._forget)

    def _remember(self, connection, record, proxy):
        with self._holders_lock:
            self._holders[id(record)] = (time.monotonic(), threading.get_ident(), _locations(sys._getframe()))

    def _forget(self, connection, record):
        with self._holders_lock:
            self._holders.pop(id(record), None)

    def _report(self):
        now = time.monotonic()
        with self._holders_lock:
            if now - self._last_report < 30:
                return
            self._last_report = now
            holders = list(self._holders.values())
        frames = sys._current_frames()
        details = [dict(age_seconds=round(now-started, 2), checkout=site,
                        current=_locations(frames.get(thread_id)))
                   for started, thread_id, site in holders]
        logger.warning('db.pool_exhausted role=%s holders=%s', self.diagnostic_role, details)

    def _do_get(self):
        try:
            return super()._do_get()
        except TimeoutError:
            self._report()
            raise
