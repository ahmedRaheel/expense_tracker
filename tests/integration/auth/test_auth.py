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




async def test_register(client):
    r = await client.post(f"{API}/auth/register", json={"email": "a@example.com", "password": "SecretPassword#123", "base_currency": "PKR"})
    assert r.status_code == 201 and "password_hash" not in r.json()


async def test_register_duplicate(client):
    await make_user(client)
    r = await client.post(f"{API}/auth/register", json={"email": "ALPHA@example.com", "password": "SecretPassword#123", "base_currency": "PKR"})
    assert r.status_code == 409


@pytest.mark.parametrize("password", ["short", "12345678901"])
async def test_register_rejects_short_password(client, password):
    r = await client.post(f"{API}/auth/register", json={"email": "a@example.com", "password": password})
    assert r.status_code == 422


async def test_register_rejects_unsupported_currency(client):
    r = await client.post(f"{API}/auth/register", json={"email": "a@example.com", "password": "SecretPassword#123", "base_currency": "BTC"})
    assert r.status_code == 422


async def test_login_issues_pair(client):
    user = await make_user(client)
    assert user["token"] and user["refresh"]


async def test_login_bad_credentials(client):
    await make_user(client)
    r = await client.post(f"{API}/auth/login", json={"email": "alpha@example.com", "password": "wrong"})
    assert r.status_code == 401


async def test_login_unknown_email(client):
    r = await client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert r.status_code == 401


async def test_sixth_failure_rate_limited(client):
    await make_user(client)
    for _ in range(5):
        r = await client.post(f"{API}/auth/login", json={"email": "alpha@example.com", "password": "wrong"})
        assert r.status_code == 401
    r = await client.post(f"{API}/auth/login", json={"email": "alpha@example.com", "password": "wrong"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


async def test_refresh_rotates_pair(client):
    user = await make_user(client)
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": user["refresh"]})
    assert r.status_code == 200 and r.json()["refresh_token"] != user["refresh"]


async def test_refresh_replay_revokes_all(client):
    user = await make_user(client)
    first = await client.post(f"{API}/auth/refresh", json={"refresh_token": user["refresh"]})
    second = await client.post(f"{API}/auth/refresh", json={"refresh_token": user["refresh"]})
    assert first.status_code == 200 and second.status_code == 401
    third = await client.post(f"{API}/auth/refresh", json={"refresh_token": first.json()["refresh_token"]})
    assert third.status_code == 401
    # Replay also invalidates all outstanding *access* JWTs via user session_version.
    old_access = await client.get(f"{API}/categories", headers=user["headers"])
    assert old_access.status_code == 401
    rotated_access = await client.get(f"{API}/categories", headers={"Authorization": "Bearer " + first.json()["access_token"]})
    assert rotated_access.status_code == 401


async def test_logout_revokes_refresh(client):
    user = await make_user(client)
    r = await client.post(f"{API}/auth/logout", headers=user["headers"], json={"refresh_token": user["refresh"]})
    assert r.status_code == 204
    again = await client.post(f"{API}/auth/refresh", json={"refresh_token": user["refresh"]})
    assert again.status_code == 401


async def test_protected_endpoint_requires_token(client):
    r = await client.get(f"{API}/categories")
    assert r.status_code == 401


async def test_invalid_access_token(client):
    r = await client.get(f"{API}/categories", headers={"Authorization": "Bearer INVALID"})
    assert r.status_code == 401

