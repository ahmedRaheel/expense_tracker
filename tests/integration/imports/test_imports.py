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




async def test_csv_import_mixed_rows(client):
    user = await make_user(client)
    await make_category(client, user, name="Food")
    data = b"date,amount,currency,category_name,description\n" + date.today().isoformat().encode() + b",10.00,PKR,Food,Coffee\n" + date.today().isoformat().encode() + b",-3,PKR,Food,Bad\n"
    r = await client.post(f"{API}/expenses/import", headers=user["headers"], files={"file": ("import.csv", data, "text/csv")})
    assert r.status_code == 202, r.text
    await process_import(UUID(r.json()["id"]))
    status = await client.get(f"{API}/imports/{r.json()['id']}", headers=user["headers"])
    assert status.status_code == 200 and status.json()["rows_done"] == 1 and status.json()["rows_failed"] == 1
    assert status.json()["errors"][0]["row_number"] == 3


async def test_csv_upload_twice_same_job_id(client):
    user = await make_user(client)
    data = b"date,amount,currency,category_name\n2026-10-01,10,PKR,Food\n"
    first = await client.post(f"{API}/expenses/import", headers=user["headers"], files={"file": ("one.csv", data, "text/csv")})
    second = await client.post(f"{API}/expenses/import", headers=user["headers"], files={"file": ("two.csv", data, "text/csv")})
    assert first.status_code == second.status_code == 202 and first.json()["id"] == second.json()["id"]


async def test_csv_job_other_user_404(client):
    one = await make_user(client)
    two = await make_user(client, "beta@example.com")
    r = await client.post(f"{API}/expenses/import", headers=one["headers"], files={"file": ("one.csv", b"a,b\n1,2\n", "text/csv")})
    status = await client.get(f"{API}/imports/{r.json()['id']}", headers=two["headers"])
    assert status.status_code == 404

