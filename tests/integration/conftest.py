"""All integration tests target a REAL, isolated PostgreSQL database."""
import os
from datetime import date, timedelta
from pathlib import Path
from decimal import Decimal

# Must be configured BEFORE application modules create their async engine.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://expense:test-only-password@localhost:5435/expenses_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/1")
os.environ.setdefault("JWT_SECRET", "local-test-signing-secret-only-32-characters-minimum")
os.environ.setdefault("IMPORT_SPOOL_DIR", ".data/imports-test")

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.main.config import get_settings
from src.infrastructure.database.session import engine, SessionFactory
from src.domain.models.base import Base
from src.main.app import app
from src.domain.models.rates import ExchangeRate
from scripts.seed_rates import RATES


@pytest.fixture(autouse=True)
async def clean_db(tmp_path):
    # Destructive TRUNCATE/Redis FLUSHDB are allowed ONLY against dedicated test resources.
    url = make_url(get_settings().database_url)
    assert url.database == "expenses_test", "REFUSING to truncate a non-test DB"
    assert url.get_backend_name() == "postgresql", "PostgreSQL is required, not SQLite"
    assert get_settings().redis_url.rstrip("/").endswith("/1"), "REFUSING to flush non-test Redis DB"
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            # TRUNCATE CASCADE for test isolation; identifiers come only from SQLAlchemy metadata.
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
    today = date.today()
    rates = [{"currency": code, "valid_on": today - timedelta(days=i), "rate_to_usd": value}
             for code, value in RATES.items() for i in range(90)]
    async with SessionFactory.begin() as session:
        await session.execute(pg_insert(ExchangeRate).values(rates))
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    await redis.flushdb()
    app.state.redis = redis
    get_settings().import_spool_dir = str(tmp_path)
    yield
    await redis.aclose()
    await engine.dispose()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver") as c:
        yield c


async def make_user(client, email="alpha@example.com", *, base="PKR"):
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": "TestingPassword#123", "base_currency": base})
    assert resp.status_code == 201, resp.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "TestingPassword#123"})
    assert login.status_code == 200, login.text
    return {"id": resp.json()["id"], "token": login.json()["access_token"], "refresh": login.json()["refresh_token"], "headers": {"Authorization": "Bearer " + login.json()["access_token"]}}


async def make_category(client, user, *, name="Food", budget="1000.00"):
    resp = await client.post("/api/v1/categories", headers=user["headers"], json={"name": name, "monthly_budget": budget})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def make_expense(client, user, category_id, *, key="key-expense-1", amount="25.00", currency="PKR", day=None, description="Shopping"):
    resp = await client.post("/api/v1/expenses", headers={**user["headers"], "Idempotency-Key": key}, json={
        "category_id": category_id, "amount": amount, "currency": currency,
        "spent_on": (day or date.today()).isoformat(), "description": description,
    })
    assert resp.status_code == 201, resp.text
    return resp
