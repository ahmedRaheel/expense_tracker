from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.domain.models.categories import Category
from src.domain.models.outbox import OutboxEvent
from src.usecase.context.identity import CurrentUser
from src.domain.policies.budget import crossed_thresholds
from src.infrastructure.adapters.rates import month_total


async def locked_category(session: AsyncSession, *, category_id: UUID, user_id: UUID) -> Category:
    from src.usecase.errors import AppError
    cat = await session.scalar(select(Category).where(Category.id == category_id, Category.user_id == user_id).with_for_update())
    if cat is None:
        raise AppError(404, "CATEGORY_NOT_FOUND", "Category not found")
    return cat


def emit_crossings(session: AsyncSession, category: Category, month: date, before: Decimal, after: Decimal) -> bool:
    events = crossed_thresholds(category.monthly_budget, before, after)
    for event in events:
        session.add(OutboxEvent(event_type="budget.crossed", payload={"user_id": str(category.user_id), "category_id": str(category.id), "month": month.isoformat(), "level": event.level, "total": str(event.total)}))
    return bool(events)


async def create_category(session: AsyncSession, user: CurrentUser, payload: "CategoryCreate") -> "CategoryDTO":
    from src.usecase.errors import AppError
    from src.usecase.dto.categories import CategoryDTO
    name = payload.name
    if await session.scalar(select(Category.id).where(Category.user_id == user.id, Category.normalized_name == name.casefold())):
        raise AppError(409, "CATEGORY_EXISTS", "Category already exists")
    category = Category(user_id=user.id, name=name, normalized_name=name.casefold(), monthly_budget=payload.monthly_budget)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return CategoryDTO(id=category.id, name=category.name, monthly_budget=category.monthly_budget)


async def list_categories(session: AsyncSession, user: CurrentUser) -> list["CategoryDTO"]:
    from sqlalchemy import text
    from src.infrastructure.database.session import utcnow
    from src.usecase.errors import AppError
    from src.usecase.dto.categories import CategoryDTO
    start = utcnow().date().replace(day=1)
    query = text("""
        SELECT c.id,c.name,c.monthly_budget,
          ROUND(COALESCE(SUM(CASE WHEN e.currency=:base THEN e.amount
             ELSE e.amount * src.rate_to_usd / dest.rate_to_usd END), 0),2) AS current_month_spend,
          COUNT(e.id) FILTER (WHERE e.currency <> :base AND
              (src.rate_to_usd IS NULL OR dest.rate_to_usd IS NULL)) AS missing,
          CASE WHEN c.monthly_budget > 0 THEN ROUND(COALESCE(SUM(
              CASE WHEN e.currency=:base THEN e.amount
              ELSE e.amount * src.rate_to_usd / dest.rate_to_usd END),0)
              /c.monthly_budget * 100, 2) END AS percentage_used
        FROM categories c
        LEFT JOIN expenses e ON e.category_id=c.id
            AND e.spent_on >= :start AND e.spent_on < (:start + INTERVAL '1 month')
        LEFT JOIN LATERAL (SELECT rate_to_usd FROM exchange_rates
             WHERE currency=e.currency AND valid_on<=e.spent_on ORDER BY valid_on DESC LIMIT 1) src ON TRUE
        LEFT JOIN LATERAL (SELECT rate_to_usd FROM exchange_rates
             WHERE currency=:base AND valid_on<=e.spent_on ORDER BY valid_on DESC LIMIT 1) dest ON TRUE
        WHERE c.user_id=:user_id
        GROUP BY c.id,c.name,c.monthly_budget
        ORDER BY c.name,c.id
    """)
    rows = (await session.execute(query, {"user_id": user.id, "base": user.base_currency, "start": start})).mappings().all()
    if any(row["missing"] for row in rows):
        raise AppError(422, "RATE_NOT_FOUND", "Missing currency conversion rates")
    return [CategoryDTO(**{k: v for k, v in row.items() if k != "missing"}) for row in rows]
