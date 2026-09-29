"""Disk-budgeted R2 materialization with cross-process reader pins.

Only files in this disposable cache are evicted. Uploads/local-only originals
are never cache victims. A scope must outlive all readers, including responses.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import fcntl
import hashlib
import os
from pathlib import Path
import tempfile
import time
import uuid

class ReaderScope(dict):
    def __init__(self):
        super().__init__()
        self.uploads = {}

    def close(self):
        for handle in self.values():
            handle.close()
        for path, identity in self.uploads.items():
            try:
                current = path.stat()
                if (current.st_ino, current.st_mtime_ns, current.st_size) == identity:
                    path.unlink()
            except FileNotFoundError:
                pass


def uploaded(path):
    readers = _scope.get()
    if readers is not None:
        stat = path.stat()
        readers.uploads[path] = (stat.st_ino, stat.st_mtime_ns, stat.st_size)


_scope = ContextVar('r2_materialization_scope', default=None)


class CacheCapacityError(RuntimeError):
    pass


def root():
    path = Path(os.getenv('R2_CACHE_DIR', str(Path(tempfile.gettempdir()) / 'dental-r2-cache')))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def budget():
    return max(1, int(os.getenv('R2_CACHE_MAX_BYTES', str(256 * 1024 * 1024))))


@contextmanager
def _lock(path):
    with path.open('a+b') as handle:
        # Do not occupy worker threads indefinitely behind slow downloads.
        deadline = time.monotonic() + 5
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise CacheCapacityError('Object cache is busy; retry later')
                time.sleep(0.02)
        yield handle


@contextmanager
def scope():
    current = _scope.get()
    if current is not None:
        yield current
        return
    pins = ReaderScope()
    token = _scope.set(pins)
    try:
        yield pins
    finally:
        _scope.reset(token)
        pins.close()


def scoped(function):
    from functools import wraps
    @wraps(function)
    def run(*args, **kwargs):
        with scope():
            return function(*args, **kwargs)
    return run


def _pointer(key):
    return root() / (hashlib.sha256(key.encode()).hexdigest() + '.ref')


def invalidate(key):
    with _lock(root() / '.allocation.lock'):
        _pointer(key).unlink(missing_ok=True)


def _pin(path, pins):
    handle = path.open('rb')
    fcntl.flock(handle, fcntl.LOCK_SH)
    pins[str(path)] = handle
    os.utime(path, None)
    return path


def _make_room(required):
    directory = root()
    files = list(directory.glob('*.data*'))
    used = sum(p.stat().st_size for p in files if p.exists())
    if required > budget():
        raise CacheCapacityError('Object exceeds the materialization budget')
    for path in sorted(files, key=lambda p: p.stat().st_mtime):
        if used + required <= budget():
            break
        try:
            with path.open('rb') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                used -= path.stat().st_size
                path.unlink()
        except (BlockingIOError, FileNotFoundError):
            continue
    if used + required > budget():
        raise CacheCapacityError('Object cache is full of active readers; retry later')
    # Remove references to evicted generations; no source object is touched.
    for pointer in directory.glob('*.ref'):
        try:
            if not (directory / pointer.read_text()).is_file():
                pointer.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def materialize(key, *, metadata, download):
    pins = _scope.get()
    if pins is None:
        raise RuntimeError('R2 materialization requires an object_cache.scope()')
    directory = root()
    pointer = _pointer(key)
    with _lock(directory / '.allocation.lock'):
        if pointer.is_file():
            path = directory / pointer.read_text()
            if path.is_file():
                if str(path) not in pins:
                    _pin(path, pins)
                return path
        size = int(metadata()['ContentLength'])
        _make_room(size)
        # The suffix remains usable by PDF/image readers. The generation is
        # immutable; replacing an object never changes an active reader's file.
        suffix = Path(key).suffix[:12]
        path = directory / (uuid.uuid4().hex + '.data' + suffix)
        try:
            download(path, size)
            if path.stat().st_size != size:
                raise IOError('Object changed during materialization')
            _pin(path, pins)
            temporary = pointer.with_suffix('.new')
            temporary.write_text(path.name)
            temporary.replace(pointer)
        except BaseException:
            handle = pins.pop(str(path), None)
            if handle:
                handle.close()
            path.unlink(missing_ok=True)
            raise
        return path


class StorageScopeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope_, receive, send):
        from anyio import to_thread
        readers = ReaderScope()
        token = _scope.set(readers)
        try:
            await self.app(scope_, receive, send)
        finally:
            _scope.reset(token)
            await to_thread.run_sync(readers.close)
