import base64
import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, insert, or_, select, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.main.config import get_settings
from src.usecase.validator import require_idempotency_key
from src.infrastructure.database.session import utcnow
from src.usecase.errors import AppError
from src.domain.models.categories import Category
from src.domain.models.expenses import Expense, IdempotencyRecord
from src.domain.models.receipts import ReceiptCleanup
from src.usecase.context.identity import CurrentUser
from src.usecase.dto.expenses import ExpenseCreate, ExpenseDTO, ExpensePatch, ExpenseResults
from src.infrastructure.adapters.categories import emit_crossings, locked_category
from src.infrastructure.adapters.rates import first_of_month, month_total, to_base


def body_digest(payload: ExpenseCreate) -> str:
    canon = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def filter_digest(filters: dict) -> str:
    return hashlib.sha256(json.dumps(filters, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def encode_cursor(*, spent_on: date, expense_id: UUID, as_of: datetime, filters_hash: str) -> str:
    raw = json.dumps({"date": spent_on.isoformat(), "id": str(expense_id), "as_of": as_of.isoformat(), "filters": filters_hash}, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    mac = hmac.new(get_settings().jwt_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + "." + mac


def decode_cursor(value: str, filters_hash: str) -> tuple[date, UUID, datetime]:
    try:
        encoded, mac = value.split(".", 1)
        expected = hmac.new(get_settings().jwt_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("Invalid signature")
        obj = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if obj["filters"] != filters_hash:
            raise ValueError("Filters changed between pages")
        return date.fromisoformat(obj["date"]), UUID(obj["id"]), datetime.fromisoformat(obj["as_of"])
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise AppError(400, "INVALID_CURSOR", "Invalid cursor or changed filters") from exc


async def poke_worker(redis_client):
    try:
        await redis_client.lpush("outbox:wakeup", "1")
    except Exception:
        # Outbox is durable in PostgreSQL; the worker also polls on a timer.
        pass


async def create_expense(session: AsyncSession, user: CurrentUser, payload: ExpenseCreate, key: str, redis_client) -> tuple[dict, bool]:
    require_idempotency_key(key)
    digest = body_digest(payload)
    now = utcnow()
    async with session.begin():
        # Expired record can be replaced. Unique constraint serializes parallel requests.
        await session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.user_id == user.id, IdempotencyRecord.key == key, IdempotencyRecord.expires_at <= now))
        reserved = await session.execute(pg_insert(IdempotencyRecord).values(
            user_id=user.id, key=key, request_hash=digest, expires_at=now + timedelta(hours=24), response_body=None,
        ).on_conflict_do_nothing(index_elements=["user_id", "key"]).returning(IdempotencyRecord.id))
        if reserved.scalar_one_or_none() is None:
            record = await session.scalar(select(IdempotencyRecord).where(IdempotencyRecord.user_id == user.id, IdempotencyRecord.key == key))
            if record is None:
                raise AppError(409, "RETRY_REQUEST", "Concurrent request in progress")
            if record.request_hash != digest:
                raise AppError(422, "IDEMPOTENCY_CONFLICT", "Idempotency key used with a different request body")
            if record.response_body is None:
                raise AppError(409, "RETRY_REQUEST", "Concurrent request in progress")
            return record.response_body, True

        cat = await locked_category(session, category_id=payload.category_id, user_id=user.id)
        await to_base(session, payload.amount, payload.currency, user.base_currency, payload.spent_on)
        month = first_of_month(payload.spent_on)
        before = await month_total(session, cat.id, user.base_currency, month)
        expense = Expense(user_id=user.id, category_id=cat.id, amount=payload.amount, currency=payload.currency, description=payload.description, spent_on=payload.spent_on, version=1)
        session.add(expense)
        await session.flush()
        await session.refresh(expense)
        after = await month_total(session, cat.id, user.base_currency, month)
        emit_crossings(session, cat, month, before, after)
        view = ExpenseDTO.model_validate(expense).model_dump(mode="json")
        await session.execute(update(IdempotencyRecord).where(IdempotencyRecord.user_id == user.id, IdempotencyRecord.key == key).values(response_body=view))
    await poke_worker(redis_client)
    return view, False


async def get_expense(session: AsyncSession, user: CurrentUser, expense_id: UUID) -> ExpenseDTO:
    row = await session.scalar(select(Expense).where(Expense.id == expense_id, Expense.user_id == user.id))
    if row is None:
        raise AppError(404, "EXPENSE_NOT_FOUND", "Expense not found")
    return ExpenseDTO.model_validate(row)


async def list_expenses(
    session: AsyncSession, user: CurrentUser, *, cursor: str | None, limit: int,
    category_id: UUID | None, date_from: date | None, date_to: date | None,
    min_amount: Decimal | None, max_amount: Decimal | None, currency: str | None, q: str | None,
) -> ExpenseResults:
    filters = {"category_id": category_id, "date_from": date_from, "date_to": date_to,
               "min_amount": min_amount, "max_amount": max_amount, "currency": currency, "q": q}
    fingerprint = filter_digest(filters)
    if cursor:
        last_date, last_id, as_of = decode_cursor(cursor, fingerprint)
    else:
        as_of = (await session.execute(select(text("clock_timestamp()")))).scalar_one()
        last_date = last_id = None
    stmt = select(Expense.__table__).where(Expense.user_id == user.id, Expense.created_at <= as_of)
    if category_id:
        stmt = stmt.where(Expense.category_id == category_id)
    if date_from:
        stmt = stmt.where(Expense.spent_on >= date_from)
    if date_to:
        stmt = stmt.where(Expense.spent_on <= date_to)
    if min_amount is not None:
        stmt = stmt.where(Expense.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Expense.amount <= max_amount)
    if currency:
        stmt = stmt.where(Expense.currency == currency)
    if q:
        needle = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Expense.description.ilike(f"%{needle}%", escape="\\"))
    if last_date and last_id:
        stmt = stmt.where(or_(Expense.spent_on < last_date, and_(Expense.spent_on == last_date, Expense.id < last_id)))
    stmt = stmt.order_by(Expense.spent_on.desc(), Expense.id.desc()).limit(limit + 1)
    rows = [dict(r) for r in (await session.execute(stmt)).mappings().all()]
    has_more = len(rows) > limit
    items = [ExpenseDTO.model_validate(row) for row in rows[:limit]]
    next_cursor = encode_cursor(spent_on=items[-1].spent_on, expense_id=items[-1].id, as_of=as_of, filters_hash=fingerprint) if has_more and items else None
    return ExpenseResults(items=items, next_cursor=next_cursor)


async def update_expense(session: AsyncSession, user: CurrentUser, expense_id: UUID, expected_version: int, payload: ExpensePatch, redis_client) -> ExpenseDTO:
    async with session.begin():
        old = await session.scalar(select(Expense).where(Expense.id == expense_id, Expense.user_id == user.id))
        if old is None:
            raise AppError(404, "EXPENSE_NOT_FOUND", "Expense not found")
        new_cat_id = payload.category_id or old.category_id
        new_month = first_of_month(payload.spent_on or old.spent_on)
        old_month = first_of_month(old.spent_on)
        # Lock in deterministic UUID order to prevent deadlocks in cross-category moves.
        cats = {}
        for cid in sorted({old.category_id, new_cat_id}, key=str):
            cats[cid] = await locked_category(session, category_id=cid, user_id=user.id)
        affected = {(old.category_id, old_month), (new_cat_id, new_month)}
        before = {(cid, month): await month_total(session, cid, user.base_currency, month) for cid, month in affected}
        changes = payload.model_dump(exclude_unset=True)
        await to_base(session, changes.get("amount", old.amount), changes.get("currency", old.currency), user.base_currency, changes.get("spent_on", old.spent_on))
        stmt = (update(Expense).where(Expense.id == expense_id, Expense.user_id == user.id, Expense.version == expected_version)
                .values(**changes, version=Expense.version + 1, updated_at=utcnow()).returning(Expense.__table__))
        updated = (await session.execute(stmt)).mappings().first()
        if updated is None:
            raise AppError(412, "VERSION_CONFLICT", "Expense has been modified; fetch a new ETag")
        for cid, month in affected:
            after = await month_total(session, cid, user.base_currency, month)
            emit_crossings(session, cats[cid], month, before[(cid, month)], after)
        result = ExpenseDTO.model_validate(dict(updated))
    await poke_worker(redis_client)
    return result


async def delete_expense(session: AsyncSession, user: CurrentUser, expense_id: UUID, redis_client) -> None:
    async with session.begin():
        old = await session.scalar(select(Expense).where(Expense.id == expense_id, Expense.user_id == user.id))
        if old is None:
            raise AppError(404, "EXPENSE_NOT_FOUND", "Expense not found")
        cat = await locked_category(session, category_id=old.category_id, user_id=user.id)
        month = first_of_month(old.spent_on)
        before = await month_total(session, cat.id, user.base_currency, month)
        if old.receipt_key:
            session.add(ReceiptCleanup(object_key=old.receipt_key))
        await session.delete(old)
        await session.flush()
        after = await month_total(session, cat.id, user.base_currency, month)
    await poke_worker(redis_client)
