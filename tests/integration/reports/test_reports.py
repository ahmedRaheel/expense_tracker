import asyncio
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select, text, update, delete
from src.infrastructure.database.session import SessionFactory
from src.domain.models.expenses import Expense, IdempotencyRecord
from src.domain.models.rates import ExchangeRate
from src.domain.models.notifications import Notification
from src.domain.models.outbox import OutboxEvent
from src.domain.models.receipts import ReceiptCleanup
from src.infrastructure.adapters.import_worker import process_import
from src.infrastructure.worker import process_outbox_batch
from src.infrastructure.adapters.s3 import detect_content_type
from tests.integration.conftest import make_user, make_category, make_expense

pytestmark = pytest.mark.integration
API = "/api/v1"




async def test_monthly_report_mixed_currency_with_rate_fallback(client):
    user = await make_user(client, base="USD")
    cat = await make_category(client, user, budget="1000")
    today = date.today()
    await make_expense(client, user, cat, key="usd", amount="10", currency="USD")
    await make_expense(client, user, cat, key="eur", amount="10", currency="EUR")
    async with SessionFactory.begin() as session:
        await session.execute(delete(ExchangeRate).where(ExchangeRate.currency == "EUR", ExchangeRate.valid_on == today))
    r = await client.get(f"{API}/reports/monthly", headers=user["headers"], params={"year": today.year, "month": today.month})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["grand_total"]) == Decimal("20.80")


async def test_monthly_report_previous_month_delta(client):
    user = await make_user(client)
    cat = await make_category(client, user)
    today = date.today()
    previous = (today.replace(day=1) - timedelta(days=1))
    await make_expense(client, user, cat, key="last", amount="30", day=previous)
    await make_expense(client, user, cat, key="this", amount="100", day=today)
    r = await client.get(f"{API}/reports/monthly", headers=user["headers"], params={"year": today.year, "month": today.month})
    assert r.status_code == 200
    assert Decimal(r.json()["categories"][0]["change_from_last_month"]) == Decimal("70")

