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




async def test_budget_alert_once_even_if_reprocessed(client):
    user = await make_user(client)
    cat = await make_category(client, user, budget="100")
    await make_expense(client, user, cat, amount="85")
    assert await process_outbox_batch() == 1
    async with SessionFactory.begin() as session:
        await session.execute(update(OutboxEvent).values(processed_at=None))
    await process_outbox_batch()
    response = await client.get(f"{API}/notifications", headers=user["headers"])
    assert response.status_code == 200
    assert [n["level"] for n in response.json()] == [80]


async def test_budget_100_alert(client):
    user = await make_user(client)
    cat = await make_category(client, user, budget="100")
    await make_expense(client, user, cat, amount="150")
    await process_outbox_batch()
    response = await client.get(f"{API}/notifications", headers=user["headers"])
    assert sorted(n["level"] for n in response.json()) == [80,100]

