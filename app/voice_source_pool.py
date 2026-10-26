"""Fixed workers plus bounded running/queued admission; no caller-runs fallback."""
import threading
from concurrent.futures import ThreadPoolExecutor


class BoundedPool:
    def __init__(self, workers, capacity, name):
        self._slots = threading.BoundedSemaphore(capacity)
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)

    def submit(self, fn, *args):
        if not self._slots.acquire(blocking=False):
            return None
        try:
            future = self._pool.submit(fn, *args)
        except Exception:
            self._slots.release()
            raise
        future.add_done_callback(lambda _: self._slots.release())
        return future

    def shutdown(self):
        self._pool.shutdown(wait=True, cancel_futures=True)
