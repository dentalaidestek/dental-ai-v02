"""Short process-local cache of maintenance flags; never caches identities."""
import threading
import time

_lock = threading.Lock()
_value = None
_until = 0


def get(loader):
    global _value, _until
    with _lock:
        if _value is None or time.monotonic() >= _until:
            _value = loader()
            _until = time.monotonic() + 2
        return dict(_value)


def invalidate():
    global _until
    with _lock:
        _until = 0
