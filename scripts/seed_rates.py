"""Seed 90 calendar days of demonstrative rates. These are sample values, NOT market data."""
import asyncio
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.infrastructure.database.session import SessionFactory
from src.domain.models.rates import ExchangeRate

RATES = {"USD": Decimal("1.0000000000"), "PKR": Decimal("0.0036000000"),
         "AED": Decimal("0.2722940000"), "EUR": Decimal("1.0800000000")}


async def seed():
    today = date.today()
    values = [{"currency": ccy, "valid_on": today - timedelta(days=i), "rate_to_usd": rate}
              for i in range(90) for ccy, rate in RATES.items()]
    async with SessionFactory.begin() as session:
        statement = pg_insert(ExchangeRate).values(values)
        await session.execute(statement.on_conflict_do_update(
            index_elements=["currency", "valid_on"], set_={"rate_to_usd": statement.excluded.rate_to_usd}))
    print("Seeded example PKR/AED/USD/EUR exchange rates for 90 days (NOT live market rates).")


if __name__ == "__main__":
    asyncio.run(seed())
