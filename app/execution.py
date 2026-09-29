"""Explicit synchronous boundaries for ASGI handlers and loop callbacks."""
from functools import partial, wraps
import asyncio
import threading
from contextlib import contextmanager
from anyio import from_thread, to_thread


class CapacityExceeded(RuntimeError):
    pass


class WorkGate:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._slots = threading.BoundedSemaphore(capacity)

    @contextmanager
    def enter(self):
        if not self._slots.acquire(blocking=False):
            raise CapacityExceeded("Service capacity is occupied")
        try:
            yield
        finally:
            self._slots.release()


def offload(function):
    """Keep public async contracts; own all SQL/file work in one AnyIO thread.

    An async callback inside the synchronous implementation must use
    on_loop(), which returns to the ASGI loop without creating a second loop.
    Sessions are never passed between concurrent workers.
    """
    @wraps(function)
    async def wrapper(*args, **kwargs):
        return await to_thread.run_sync(partial(function, *args, **kwargs))
    return wrapper


def on_loop(function, *args, **kwargs):
    return from_thread.run(partial(function, *args, **kwargs))


class LoopWakeup:
    """Thread-safe, restartable wakeup for lifespan-owned durable schedulers."""
    def __init__(self):
        self.loop = None
        self.event = None

    def bind(self):
        self.loop = asyncio.get_running_loop()
        self.event = asyncio.Event()

    def set(self):
        if self.loop is not None and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.event.set)

    def clear(self):
        if self.event is not None:
            self.event.clear()

    async def wait(self):
        if self.loop is not asyncio.get_running_loop():
            self.bind()
        await self.event.wait()
