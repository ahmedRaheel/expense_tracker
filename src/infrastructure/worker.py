"""Run: python -m src.worker. Durable DB outbox + Redis wakeup hint, async import and receipt cleanup."""
import asyncio
import logging
from datetime import date, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.main.config import get_settings
from src.infrastructure.database.session import SessionFactory, utcnow
from src.domain.models.notifications import Notification
from src.domain.models.outbox import OutboxEvent
from src.domain.models.receipts import ReceiptCleanup
from src.infrastructure.adapters.import_worker import claim_import_job, process_import
from src.infrastructure.adapters.s3 import S3Storage

log = logging.getLogger(__name__)


async def process_outbox_batch(batch_size: int = 100) -> int:
    async with SessionFactory.begin() as session:
        events = (await session.scalars(select(OutboxEvent).where(
            OutboxEvent.processed_at.is_(None), OutboxEvent.available_at <= utcnow()
        ).order_by(OutboxEvent.available_at, OutboxEvent.id).with_for_update(skip_locked=True).limit(batch_size))).all()
        for ev in events:
            try:
                if ev.event_type == "budget.crossed":
                    p = ev.payload
                    await session.execute(pg_insert(Notification).values(
                        user_id=UUID(p["user_id"]), category_id=UUID(p["category_id"]),
                        month=date.fromisoformat(p["month"]), level=int(p["level"]),
                        message=f"Category reached {p['level']}% of monthly budget (total {p['total']}).",
                    ).on_conflict_do_nothing(constraint="uq_notification_threshold_month"))
                else:
                    raise ValueError("Unknown outbox event type: " + ev.event_type)
                ev.processed_at = utcnow()
            except Exception as exc:
                ev.attempts += 1
                ev.last_error = str(exc)[:1000]
                ev.available_at = utcnow() + timedelta(seconds=min(300, 2 ** min(ev.attempts, 8)))
        return len(events)


async def process_receipt_cleanup(batch_size: int = 20) -> int:
    """Deletes are idempotent; retry if S3 is unavailable, even after process crash."""
    async with SessionFactory.begin() as session:
        jobs = (await session.scalars(select(ReceiptCleanup).where(
            ReceiptCleanup.completed_at.is_(None), ReceiptCleanup.available_at <= utcnow()
        ).order_by(ReceiptCleanup.available_at).with_for_update(skip_locked=True).limit(batch_size))).all()
        for job in jobs:
            try:
                await S3Storage().delete_object(job.object_key)
                job.completed_at = utcnow()
            except Exception as exc:
                job.attempts += 1
                job.last_error = str(exc)[:1000]
                job.available_at = utcnow() + timedelta(seconds=min(300, 2 ** min(job.attempts, 8)))
        return len(jobs)


async def main():
    logging.basicConfig(level=logging.INFO)
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        while True:
            try:
                outbox = await process_outbox_batch()
                cleaned = await process_receipt_cleanup()
                job = await claim_import_job()
                if job:
                    await process_import(job)
                if outbox or cleaned or job:
                    continue
                try:
                    await redis.brpop("outbox:wakeup", timeout=2)
                except Exception:
                    await asyncio.sleep(2)  # DB polling remains available if Redis fails
            except Exception:
                log.exception("Worker iteration failed; will retry")
                await asyncio.sleep(2)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
