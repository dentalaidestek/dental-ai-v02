"""Dedicated consultation deadline worker entrypoint.

Run with: python -m app.deadline_worker
The web service can set DENTALAI_DEADLINE_EXECUTION=external when this process is deployed separately.
No Redis/Kafka is required; PostgreSQL is the durable queue and wake-up bus.
"""
import asyncio

from app import main


async def run() -> None:
    from app.migrate import require_schema
    await asyncio.to_thread(require_schema, main.engine)
    main._consultation_deadline_wakeup.bind()
    listener = asyncio.create_task(main._postgres_event_listener(listen_deadline=True, listen_realtime=False))
    worker = asyncio.create_task(main._consultation_deadline_worker())
    try:
        await worker
    finally:
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(run())
