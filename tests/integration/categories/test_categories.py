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




async def test_category_create(client):
    user = await make_user(client)
    category_id = await make_category(client, user)
    assert UUID(category_id)


async def test_duplicate_category_casefold(client):
    user = await make_user(client)
    await make_category(client, user, name="Food")
    r = await client.post(f"{API}/categories", headers=user["headers"], json={"name": "food"})
    assert r.status_code == 409


async def test_category_invalid_budget(client):
    user = await make_user(client)
    r = await client.post(f"{API}/categories", headers=user["headers"], json={"name": "Food", "monthly_budget": "-1.00"})
    assert r.status_code == 422


async def test_category_list_spend(client):
    user = await make_user(client)
    cid = await make_category(client, user, budget="100.00")
    await make_expense(client, user, cid, amount="25.00")
    r = await client.get(f"{API}/categories", headers=user["headers"])
    assert r.status_code == 200 and Decimal(r.json()[0]["current_month_spend"]) == Decimal("25")


async def test_other_users_category_returns_404(client):
    one = await make_user(client)
    two = await make_user(client, "beta@example.com")
    cid = await make_category(client, one)
    r = await client.post(f"{API}/expenses", headers={**two["headers"], "Idempotency-Key": "cross"}, json={
        "category_id": cid, "amount": "10.00", "currency": "PKR", "spent_on": date.today().isoformat()})
    assert r.status_code == 404

