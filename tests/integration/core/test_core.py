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




async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_invalid_json_error_format(client):
    user = await make_user(client)
    r = await client.post(f"{API}/categories", headers=user["headers"], json={"name": ""})
    assert r.status_code == 422 and "error" in r.json() and "code" in r.json()["error"]


async def test_unknown_route_error_format(client):
    r = await client.get("/not-a-route")
    assert r.status_code == 404 and "error" in r.json()

