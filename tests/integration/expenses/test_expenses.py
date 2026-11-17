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




async def test_expense_create_returns_etag(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    r = await make_expense(client, user, cid)
    assert r.headers["etag"] == '"v1"' and r.json()["version"] == 1


@pytest.mark.parametrize("amount", ["0", "-10", "10.001"])
async def test_expense_invalid_amount(client, amount):
    user = await make_user(client)
    cid = await make_category(client, user)
    r = await client.post(f"{API}/expenses", headers={**user["headers"], "Idempotency-Key": "invalid-key"}, json={
        "category_id": cid, "amount": amount, "currency": "PKR", "spent_on": date.today().isoformat(),
    })
    assert r.status_code == 422


async def test_idempotency_header_is_required(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    r = await client.post(f"{API}/expenses", headers=user["headers"], json={"category_id": cid, "amount": "10.00", "currency": "PKR", "spent_on": date.today().isoformat()})
    assert r.status_code == 422


async def test_idempotent_replay_same_response(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    first = await make_expense(client, user, cid, key="same")
    second = await make_expense(client, user, cid, key="same")
    assert first.json() == second.json() and second.headers["idempotency-replayed"] == "true"
    async with SessionFactory() as session:
        assert await session.scalar(select(text("count(*)")).select_from(Expense)) == 1


async def test_idempotent_different_body_returns_422(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    await make_expense(client, user, cid, key="same")
    r = await client.post(f"{API}/expenses", headers={**user["headers"], "Idempotency-Key": "same"}, json={
        "category_id": cid, "amount": "50.00", "currency": "PKR", "spent_on": date.today().isoformat(),
        "description": "Shopping",
    })
    assert r.status_code == 422


async def test_parallel_post_idempotency(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    payload = {"category_id": cid, "amount": "25.00", "currency": "PKR", "spent_on": date.today().isoformat(), "description": "Same"}
    async def send():
        return await client.post(f"{API}/expenses", headers={**user["headers"], "Idempotency-Key": "race-key"}, json=payload)
    a,b = await asyncio.gather(send(),send())
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
    async with SessionFactory() as session:
        assert await session.scalar(select(text("count(*)")).select_from(Expense)) == 1


async def test_other_users_expense_returns_404(client):
    one = await make_user(client)
    two = await make_user(client, "beta@example.com")
    cid = await make_category(client, one)
    expense = (await make_expense(client, one, cid)).json()
    r = await client.get(f"{API}/expenses/{expense['id']}", headers=two["headers"])
    assert r.status_code == 404


async def test_get_expense_etag(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    expense = (await make_expense(client, user, cid)).json()
    r = await client.get(f"{API}/expenses/{expense['id']}", headers=user["headers"])
    assert r.status_code == 200 and r.headers["etag"] == '"v1"'


async def test_patch_missing_if_match_428(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    expense = (await make_expense(client, user, cid)).json()
    r = await client.patch(f"{API}/expenses/{expense['id']}", headers=user["headers"], json={"description": "updated"})
    assert r.status_code == 428


async def test_patch_stale_version_412(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    expense = (await make_expense(client, user, cid)).json()
    r = await client.patch(f"{API}/expenses/{expense['id']}", headers={**user["headers"], "If-Match": '"v2"'}, json={"description": "updated"})
    assert r.status_code == 412


async def test_patch_updates_version(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    expense = (await make_expense(client, user, cid)).json()
    r = await client.patch(f"{API}/expenses/{expense['id']}", headers={**user["headers"], "If-Match": '"v1"'}, json={"description": "updated"})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.headers["etag"] == '"v2"'


async def test_parallel_patch_one_wins(client):
    user = await make_user(client)
    cid = await make_category(client, user)
    expense = (await make_expense(client, user, cid)).json()
    async def change(value):
        return await client.patch(f"{API}/expenses/{expense['id']}", headers={**user["headers"], "If-Match": '"v1"'}, json={"description": value})
    a,b = await asyncio.gather(change("device A"),change("device B"))
    assert sorted([a.status_code,b.status_code]) == [200,412]


async def test_expense_filters(client):
    user = await make_user(client)
    cat = await make_category(client, user)
    other = await make_category(client, user, name="Travel")
    await make_expense(client, user, cat, key="1", amount="25.00", description="coffee")
    await make_expense(client, user, other, key="2", amount="100.00", description="train")
    r = await client.get(f"{API}/expenses", headers=user["headers"], params={"category_id": cat, "currency": "PKR", "q": "coffee", "min_amount": "20", "max_amount": "30"})
    assert r.status_code == 200 and len(r.json()["items"]) == 1


async def test_cursor_no_duplicates_after_insert(client):
    user = await make_user(client)
    cat = await make_category(client, user)
    d = date.today()
    for i in range(5):
        await make_expense(client, user, cat, key=f"e{i}", day=d-timedelta(days=i))
    first = await client.get(f"{API}/expenses", headers=user["headers"], params={"limit": 2})
    assert first.status_code == 200
    seen = [e["id"] for e in first.json()["items"]]
    await make_expense(client, user, cat, key="newer", day=d+timedelta(days=1))
    cursor = first.json()["next_cursor"]
    while cursor:
        resp = await client.get(f"{API}/expenses", headers=user["headers"], params={"limit": 2, "cursor": cursor})
        assert resp.status_code == 200, resp.text
        seen += [e["id"] for e in resp.json()["items"]]
        cursor = resp.json()["next_cursor"]
    assert len(seen) == 5 and len(set(seen)) == 5


async def test_cursor_tampering_rejected(client):
    user = await make_user(client)
    r = await client.get(f"{API}/expenses", headers=user["headers"], params={"cursor": "bad-token"})
    assert r.status_code == 400


async def test_cursor_filter_change_rejected(client):
    user = await make_user(client)
    cat = await make_category(client, user)
    for i in range(3):
        await make_expense(client, user, cat, key=f"x{i}")
    r = await client.get(f"{API}/expenses", headers=user["headers"], params={"limit": 1})
    cursor = r.json()["next_cursor"]
    bad = await client.get(f"{API}/expenses", headers=user["headers"], params={"limit": 1, "cursor": cursor, "q": "coffee"})
    assert bad.status_code == 400


async def test_delete_expense(client):
    user = await make_user(client)
    cat = await make_category(client, user)
    expense = (await make_expense(client, user, cat)).json()
    r = await client.delete(f"{API}/expenses/{expense['id']}", headers=user["headers"])
    assert r.status_code == 204
    r = await client.get(f"{API}/expenses/{expense['id']}", headers=user["headers"])
    assert r.status_code == 404

