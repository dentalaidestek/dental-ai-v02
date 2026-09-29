"""Bounded socket writes and a thread-owned PostgreSQL LISTEN connection."""
import asyncio
from collections import deque
import os
import select
import threading

import psycopg2


class SocketWrites:
    def __init__(self):
        self.states = {}

    async def accept(self, socket):
        if len(self.states) >= int(os.getenv('DENTAL_MAX_SOCKETS', '2000')):
            await socket.close(code=1013)
            return False
        await socket.accept()
        self.states[socket] = [asyncio.Lock(), 0]
        return True

    def discard(self, socket):
        self.states.pop(socket, None)

    async def send(self, socket, payload):
        state = self.states.get(socket)
        if state is None:
            return False
        if state[1] >= 16:
            self.discard(socket)
            try:
                await asyncio.wait_for(socket.close(code=1013), 1)
            except Exception:
                pass
            return False
        state[1] += 1
        try:
            async def write():
                async with state[0]:
                    await socket.send_json(payload)
            await asyncio.wait_for(write(), timeout=3)
            return True
        except Exception:
            self.discard(socket)
            try:
                await asyncio.wait_for(socket.close(code=1013), 1)
            except Exception:
                pass
            return False
        finally:
            state[1] -= 1


socket_writes = SocketWrites()


class PostgresNotices:
    """One owning thread; bounded notices and no DB/driver work on the loop."""
    def __init__(self, dsn, channels):
        self.dsn, self.channels = dsn, channels
        self.notices = deque(maxlen=2048)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.wakeup = None
        self.thread = None

    def start(self):
        self.loop = asyncio.get_running_loop()
        self.wakeup = asyncio.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name='dental-pg-listen')
        self.thread.start()

    def _signal(self):
        try:
            self.loop.call_soon_threadsafe(self.wakeup.set)
        except RuntimeError:
            pass

    def _run(self):
        from psycopg2 import sql
        while not self.stop.is_set():
            conn = None
            try:
                conn = psycopg2.connect(self.dsn, connect_timeout=5, application_name='dental-listener')
                conn.set_session(autocommit=True)
                with conn.cursor() as cursor:
                    for channel in self.channels:
                        cursor.execute(sql.SQL('LISTEN {}').format(sql.Identifier(channel)))
                # None requests durable catchup after any listener reconnect.
                with self.lock:
                    self.notices.append(None)
                self._signal()
                while not self.stop.is_set():
                    if not select.select([conn], [], [], 0.5)[0]:
                        continue
                    conn.poll()
                    with self.lock:
                        for notice in conn.notifies:
                            if len(self.notices) == self.notices.maxlen:
                                self.notices.clear()
                                self.notices.append(None)
                            self.notices.append((notice.channel, notice.payload))
                        conn.notifies.clear()
                    self._signal()
            except Exception:
                if not self.stop.is_set():
                    self.stop.wait(2)
            finally:
                if conn is not None:
                    conn.close()

    async def batch(self):
        await self.wakeup.wait()
        self.wakeup.clear()
        with self.lock:
            batch = list(self.notices)
            self.notices.clear()
        return batch

    async def close(self):
        self.stop.set()
        if self.thread:
            await asyncio.to_thread(self.thread.join, 7)
