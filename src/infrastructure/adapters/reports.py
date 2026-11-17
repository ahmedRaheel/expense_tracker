"""Optimized PostgreSQL reporting query; no ORM graph materialization."""
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.application.context.identity import Actor
from src.application.errors import AppError
from src.application.dto.reports import MonthlyCategoryDTO, MonthlyReport

# One PostgreSQL statement. As-of rates via LATERAL; two month rows per
# category plus LAG for previous month. The query also counts missing rates.
MONTHLY_SQL = text("""
WITH month_bounds AS (
    SELECT make_date(:year, :month, 1)::date AS current_month
), months AS (
    SELECT (current_month - INTERVAL '1 month')::date AS month FROM month_bounds
    UNION ALL
    SELECT current_month FROM month_bounds
), converted AS (
    SELECT e.category_id, date_trunc('month', e.spent_on)::date AS month,
        CASE WHEN e.currency=:base THEN e.amount
            ELSE e.amount * src.rate_to_usd / dest.rate_to_usd END AS base_amount,
        CASE WHEN e.currency<>:base AND (src.rate_to_usd IS NULL OR dest.rate_to_usd IS NULL)
            THEN 1 ELSE 0 END AS missing_rate
    FROM expenses e
    LEFT JOIN LATERAL (
        SELECT r.rate_to_usd FROM exchange_rates r
        WHERE r.currency=e.currency AND r.valid_on<=e.spent_on
        ORDER BY r.valid_on DESC LIMIT 1
    ) src ON TRUE
    LEFT JOIN LATERAL (
        SELECT r.rate_to_usd FROM exchange_rates r
        WHERE r.currency=:base AND r.valid_on<=e.spent_on
        ORDER BY r.valid_on DESC LIMIT 1
    ) dest ON TRUE
    WHERE e.user_id=:user_id
      AND e.spent_on >= (SELECT current_month - INTERVAL '1 month' FROM month_bounds)
      AND e.spent_on < (SELECT current_month + INTERVAL '1 month' FROM month_bounds)
), month_totals AS (
    SELECT c.id AS category_id, c.name, c.monthly_budget, m.month,
        COALESCE(SUM(x.base_amount),0)::NUMERIC(24,2) AS total,
        COALESCE(SUM(x.missing_rate),0) AS missing_rates
    FROM categories c CROSS JOIN months m
    LEFT JOIN converted x ON x.category_id=c.id AND x.month=m.month
    WHERE c.user_id=:user_id
    GROUP BY c.id,c.name,c.monthly_budget,m.month
), lagged AS (
    SELECT *, LAG(total,1,0::NUMERIC) OVER (PARTITION BY category_id ORDER BY month) AS previous_total,
      LAG(missing_rates,1,0::NUMERIC) OVER (PARTITION BY category_id ORDER BY month) AS previous_missing_rates
    FROM month_totals
)
SELECT category_id, name, monthly_budget, total, previous_total,
    total-previous_total AS change_from_last_month,
    CASE WHEN monthly_budget>0 THEN ROUND(total/monthly_budget*100,2) END AS percentage_used,
    missing_rates, previous_missing_rates
FROM lagged WHERE month=(SELECT current_month FROM month_bounds)
ORDER BY name,category_id
""")



async def build_monthly_report(session: AsyncSession, user: Actor, year: int, month: int) -> MonthlyReport:
    rows = (await session.execute(MONTHLY_SQL, {"year": year, "month": month, "base": user.base_currency, "user_id": user.id})).mappings().all()
    if any(row["missing_rates"] or row["previous_missing_rates"] for row in rows):
        raise AppError(422, "RATE_NOT_FOUND", "Cannot report because expense-date exchange rates are missing")
    categories = [MonthlyCategoryDTO(**{k: v for k, v in row.items() if k not in ("missing_rates", "previous_missing_rates")}) for row in rows]
    return MonthlyReport(year=year, month=month, base_currency=user.base_currency,
                         categories=categories, grand_total=sum((x.total for x in categories), Decimal("0.00")))
