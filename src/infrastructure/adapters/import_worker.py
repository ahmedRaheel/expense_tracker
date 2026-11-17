"""Resumable, streaming CSV importer: PostgreSQL is its durable job queue."""
import asyncio
import csv
import itertools
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, update, insert, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import SessionFactory, utcnow
from src.domain.models.categories import Category
from src.domain.models.rates import ExchangeRate
from src.domain.models.expenses import Expense
from src.domain.models.imports import ImportJob, ImportErrorRow
from src.domain.models.auth import User
from src.application.dto.expenses import ExpenseCreate
from src.infrastructure.adapters.categories import emit_crossings, locked_category
from src.infrastructure.adapters.rates import first_of_month, month_total

BATCH_SIZE = 500
CSV_REQUIRED = {"date", "amount", "currency", "category_name"}


def inspect_csv(path: str) -> tuple[int, set[str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = set(reader.fieldnames or [])
        total = 0
        for _ in reader:
            total += 1
            if total > 100000:
                break
        return total, header


def csv_batches(path: str, skip: int):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for _ in range(skip):
            next(reader, None)
        number = skip + 2  # first physical data line is 2 (excluding multiline fields)
        while True:
            batch = list(itertools.islice(reader, BATCH_SIZE))
            if not batch:
                return
            yield [(number + i, row) for i, row in enumerate(batch)]
            number += len(batch)


async def claim_import_job() -> UUID | None:
    async with SessionFactory.begin() as db:
        job = await db.scalar(select(ImportJob).where(
            or_(ImportJob.status == "queued", (ImportJob.status == "running") & (ImportJob.lease_until < utcnow()))
        ).order_by(ImportJob.created_at).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        job.status = "running"
        job.lease_until = utcnow() + timedelta(minutes=5)
        return job.id


def rate_to_base(codes: dict[str, list[tuple[date, Decimal]]], amount: Decimal, from_ccy: str, base: str, day: date) -> Decimal:
    if from_ccy == base:
        return amount
    def find(code):
        for dt, rate in reversed(codes.get(code, [])):
            if dt <= day:
                return rate
        raise ValueError(f"Exchange rate missing for {code} on/before {day}")
    return (amount * find(from_ccy) / find(base)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def process_import(job_id: UUID) -> None:
    async with SessionFactory() as db:
        job = await db.get(ImportJob, job_id)
        if job is None:
            return
        path, processed = job.spool_path, job.processed_rows
        user = await db.get(User, job.user_id)
        categories = {c.normalized_name: c.id for c in (await db.scalars(select(Category).where(Category.user_id == user.id))).all()}
        codes = defaultdict(list)
        for r in (await db.scalars(select(ExchangeRate).order_by(ExchangeRate.valid_on))).all():
            codes[r.currency].append((r.valid_on, r.rate_to_usd))
    try:
        total, cols = await asyncio.to_thread(inspect_csv, path)
        if not CSV_REQUIRED.issubset(cols):
            raise ValueError(f"CSV headers must include: {', '.join(sorted(CSV_REQUIRED))}")
        if total > 100000:
            raise ValueError("CSV exceeds 100,000 rows; no rows imported")
        async with SessionFactory.begin() as db:
            job = await db.get(ImportJob, job_id)
            job.total_rows = total
        iterator = csv_batches(path, processed)
        while batch := await asyncio.to_thread(next, iterator, None):
            valid = []
            errors = []
            for row_number, row in batch:
                try:
                    name = " ".join((row.get("category_name") or "").split()).casefold()
                    category_id = categories.get(name)
                    if category_id is None:
                        raise ValueError("Unknown category name")
                    obj = ExpenseCreate(category_id=category_id, amount=row.get("amount"), currency=row.get("currency"), spent_on=row.get("date"), description=row.get("description") or "")
                    rate_to_base(codes, obj.amount, obj.currency, user.base_currency, obj.spent_on)
                    valid.append(obj)
                except (ValueError, ValidationError, TypeError, KeyError, ZeroDivisionError) as exc:
                    errors.append({"job_id": job_id, "row_number": row_number, "reason": str(exc)[:500]})
            async with SessionFactory.begin() as db:
                job = await db.get(ImportJob, job_id, with_for_update=True)
                # Resume safety: only process a given contiguous range once.
                if job.processed_rows >= processed + len(batch):
                    processed += len(batch)
                    continue
                affected = {(obj.category_id, first_of_month(obj.spent_on)) for obj in valid}
                cats = {}
                for cid in sorted({cat for cat, _ in affected}, key=str):
                    cats[cid] = await locked_category(db, category_id=cid, user_id=user.id)
                before = {(cid, month): await month_total(db, cid, user.base_currency, month) for cid, month in affected}
                if valid:
                    await db.execute(insert(Expense.__table__), [{
                        "id": uuid4(), "user_id": user.id, "category_id": obj.category_id,
                        "amount": obj.amount, "currency": obj.currency, "description": obj.description,
                        "spent_on": obj.spent_on, "version": 1,
                    } for obj in valid])
                if errors:
                    await db.execute(insert(ImportErrorRow.__table__), errors)
                for cid, month in affected:
                    after = await month_total(db, cid, user.base_currency, month)
                    emit_crossings(db, cats[cid], month, before[(cid, month)], after)
                job.rows_done += len(valid)
                job.rows_failed += len(errors)
                job.processed_rows += len(batch)
                job.lease_until = utcnow() + timedelta(minutes=5)
                job.updated_at = utcnow()
            processed += len(batch)
        async with SessionFactory.begin() as db:
            job = await db.get(ImportJob, job_id, with_for_update=True)
            job.status = "finished"
            job.lease_until = None
            job.updated_at = utcnow()
    except Exception as exc:
        async with SessionFactory.begin() as db:
            job = await db.get(ImportJob, job_id, with_for_update=True)
            job.status = "failed"
            job.last_error = str(exc)[:1000]
            job.lease_until = None
            job.updated_at = utcnow()
