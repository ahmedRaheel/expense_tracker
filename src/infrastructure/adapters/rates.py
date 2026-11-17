from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.application.errors import AppError
from src.domain.models.rates import ExchangeRate
from src.domain.models.expenses import Expense

TWO = Decimal("0.01")


async def to_base(session: AsyncSession, amount: Decimal, currency: str, base_currency: str, spent_on: date) -> Decimal:
    if currency == base_currency:
        return amount.quantize(TWO)

    async def rate(code: str) -> Decimal:
        return await session.scalar(
            select(ExchangeRate.rate_to_usd).where(ExchangeRate.currency == code, ExchangeRate.valid_on <= spent_on).order_by(ExchangeRate.valid_on.desc()).limit(1)
        )

    from_rate = await rate(currency)
    to_rate = await rate(base_currency)
    if from_rate is None or to_rate is None or to_rate == 0:
        raise AppError(422, "RATE_NOT_FOUND", f"Missing exchange rate for {currency}/{base_currency} on or before {spent_on}")
    return (amount * from_rate / to_rate).quantize(TWO, rounding=ROUND_HALF_UP)


async def month_total(session: AsyncSession, category_id: UUID, base_currency: str, month: date) -> Decimal:
    # SQL conversion with lateral as-of exchange rate; no ORM object materialization.
    from sqlalchemy import text
    result = await session.execute(text("""
        SELECT COALESCE(SUM(CASE WHEN e.currency = :base THEN e.amount
            ELSE e.amount * src.rate_to_usd / dest.rate_to_usd END), 0) AS total,
            COUNT(*) FILTER (WHERE e.currency <> :base AND (src.rate_to_usd IS NULL OR dest.rate_to_usd IS NULL)) AS missing
        FROM expenses e
        LEFT JOIN LATERAL (SELECT rate_to_usd FROM exchange_rates
             WHERE currency=e.currency AND valid_on <= e.spent_on ORDER BY valid_on DESC LIMIT 1) src ON TRUE
        LEFT JOIN LATERAL (SELECT rate_to_usd FROM exchange_rates
             WHERE currency=:base AND valid_on <= e.spent_on ORDER BY valid_on DESC LIMIT 1) dest ON TRUE
        WHERE e.category_id=:category_id AND e.spent_on >= :start
          AND e.spent_on < (:start + INTERVAL '1 month')
    """), {"base": base_currency, "category_id": category_id, "start": month})
    row = result.mappings().one()
    if row["missing"]:
        raise AppError(422, "RATE_NOT_FOUND", "Missing exchange rates for expense conversion")
    return Decimal(row["total"]).quantize(TWO, rounding=ROUND_HALF_UP)


def first_of_month(d: date) -> date:
    return d.replace(day=1)
