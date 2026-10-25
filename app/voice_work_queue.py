"""Bounded, process-local voice admission; never persist clinical payloads."""
import asyncio
from collections import deque
from contextlib import asynccontextmanager


class VoiceQueueBusy(ValueError):
    pass


class VoiceWorkQueue:
    def __init__(self, *, capacity=2, max_waiters=8, wait_timeout=30):
        self.capacity = capacity
        self.max_waiters = max_waiters
        self.wait_timeout = wait_timeout
        self._active = 0
        self._waiting = deque()
        self._owners = set()

    def _release(self):
        self._active -= 1
        while self._waiting:
            waiter = self._waiting.popleft()
            if not waiter.done():
                self._active += 1
                waiter.set_result(None)
                break

    @asynccontextmanager
    async def slot(self, owner):
        if owner in self._owners:
            raise VoiceQueueBusy('Bu hesap için bir muayene işlemi zaten bekliyor veya sürüyor. Taslak korunuyor.')
        waiter = None
        admitted = False
        if self._active < self.capacity and not self._waiting:
            self._active += 1
            admitted = True
        else:
            if len(self._waiting) >= self.max_waiters:
                raise VoiceQueueBusy('İşlem sırası dolu. Taslak korunuyor; biraz sonra tekrar dene.')
            waiter = asyncio.get_running_loop().create_future()
            self._waiting.append(waiter)
        self._owners.add(owner)
        try:
            if waiter is not None:
                try:
                    await asyncio.wait_for(waiter, self.wait_timeout)
                except TimeoutError:
                    raise VoiceQueueBusy('İşlem sırası için bekleme süresi doldu. Taslak korunuyor; tekrar deneyebilirsin.') from None
                admitted = True
            yield
        finally:
            self._owners.discard(owner)
            if waiter is not None:
                # Cancellation can race with a grant before await resumes.
                admitted = admitted or (waiter.done() and not waiter.cancelled())
                if waiter in self._waiting:
                    self._waiting.remove(waiter)
            if admitted:
                self._release()


def queue_for(request, *, upload=False):
    name = 'voice_upload_queue' if upload else 'voice_work_queue'
    queue = getattr(request.app.state, name, None)
    if queue is None:
        # At most two buffered audio bodies, including their processing wait.
        queue = VoiceWorkQueue(max_waiters=0) if upload else VoiceWorkQueue()
        setattr(request.app.state, name, queue)
    return queue


@asynccontextmanager
async def request_owner(request, owner):
    """One outstanding HTTP operation per account, including upload time."""
    owners = getattr(request.app.state, 'voice_request_owners', None)
    if owners is None:
        owners = request.app.state.voice_request_owners = set()
    if owner in owners:
        raise VoiceQueueBusy('Bu hesap için bir muayene işlemi zaten bekliyor veya sürüyor. Taslak korunuyor.')
    owners.add(owner)
    try:
        yield
    finally:
        owners.discard(owner)


async def run_voice_worker(request, function, *args, **kwargs):
    """Do not release admission while a cancelled HTTP task's worker still runs."""
    from starlette.concurrency import run_in_threadpool
    if await request.is_disconnected():
        raise VoiceQueueBusy('İstek bağlantısı kapandı; işlem başlatılmadı.')
    worker = asyncio.create_task(run_in_threadpool(function, *args, **kwargs))
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(worker)
            break
        except asyncio.CancelledError:
            cancelled = True
            if worker.done():
                raise
    if cancelled:
        raise asyncio.CancelledError
    return result
