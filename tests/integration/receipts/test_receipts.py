from uuid import UUID

import pytest
from sqlalchemy import select

from src.domain.models.expenses import Expense
from src.domain.models.receipts import ReceiptCleanup
from src.infrastructure.adapters.s3 import detect_content_type
from src.infrastructure.database.session import SessionFactory
from src.usecase.errors import AppError
from tests.integration.conftest import make_category, make_expense, make_user

pytestmark = pytest.mark.integration
API = "/api/v1"


class FakeReceiptStorage:
    """No AWS network calls. The real S3 adapter's magic-byte check is separately unit tested."""
    file_bytes: bytes = b"\x89PNG\r\n\x1a\nvalid-image"

    async def upload_post(self, key, content_type):
        return {"url": "https://mock.invalid/upload", "fields": {"Content-Type": content_type}}

    async def validate_object(self, key, expected_type):
        if detect_content_type(self.file_bytes) != expected_type:
            raise AppError(422, "RECEIPT_TYPE_INVALID", "File does not match declared content type")
        return len(self.file_bytes)

    async def download_url(self, key):
        return "https://mock.invalid/download"

    async def delete_object(self, key):
        return None


@pytest.fixture
def mock_storage(monkeypatch):
    fake = FakeReceiptStorage()
    monkeypatch.setattr("src.infrastructure.adapters.receipts.S3Storage", lambda: fake)
    return fake


async def create_with_receipt(client, user, cid):
    expense = (await make_expense(client, user, cid)).json()
    result = await client.post(
        f"{API}/expenses/{expense['id']}/receipt/upload-url",
        headers=user["headers"], params={"content_type": "image/png"},
    )
    assert result.status_code == 200, result.text
    return expense, result.json()


async def test_receipt_presigned_upload_and_confirm_updates_database(client, mock_storage):
    user = await make_user(client)
    cat = await make_category(client, user)
    expense, presign = await create_with_receipt(client, user, cat)
    assert presign["expires_in"] == 900
    assert presign["max_bytes"] == 5 * 1024 * 1024
    assert presign["object_key"].startswith(f"receipts/{user['id']}/{expense['id']}/")
    confirmed = await client.post(
        f"{API}/expenses/{expense['id']}/receipt/confirm",
        headers=user["headers"], json={"object_key": presign["object_key"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["expires_in"] == 900
    async with SessionFactory() as db:
        saved = await db.get(Expense, UUID(expense["id"]))
        assert saved.receipt_key == presign["object_key"]


async def test_receipt_upload_url_rejects_unsupported_content_type(client, mock_storage):
    user = await make_user(client)
    cat = await make_category(client, user)
    expense = (await make_expense(client, user, cat)).json()
    response = await client.post(
        f"{API}/expenses/{expense['id']}/receipt/upload-url",
        headers=user["headers"], params={"content_type": "application/x-msdownload"},
    )
    assert response.status_code == 422


async def test_receipt_confirm_rejects_executable_renamed_png(client, mock_storage):
    user = await make_user(client)
    cat = await make_category(client, user)
    expense, presign = await create_with_receipt(client, user, cat)
    mock_storage.file_bytes = b"MZ\x90\x00renamed-exe"
    response = await client.post(
        f"{API}/expenses/{expense['id']}/receipt/confirm",
        headers=user["headers"], json={"object_key": presign["object_key"]},
    )
    assert response.status_code == 422
    async with SessionFactory() as db:
        saved = await db.get(Expense, UUID(expense["id"]))
        assert saved.receipt_key is None


async def test_receipt_confirm_requires_issued_upload_intent(client, mock_storage):
    user = await make_user(client)
    cat = await make_category(client, user)
    expense = (await make_expense(client, user, cat)).json()
    response = await client.post(
        f"{API}/expenses/{expense['id']}/receipt/confirm",
        headers=user["headers"], json={"object_key": f"receipts/{user['id']}/{expense['id']}/unissued.png"},
    )
    assert response.status_code == 422


async def test_receipt_cannot_be_accessed_by_another_user(client, mock_storage):
    one = await make_user(client)
    two = await make_user(client, "other@example.com")
    cat = await make_category(client, one)
    expense, _ = await create_with_receipt(client, one, cat)
    response = await client.get(f"{API}/expenses/{expense['id']}/receipt", headers=two["headers"])
    assert response.status_code == 404


async def test_deleting_expense_queues_receipt_for_eventual_cleanup(client, mock_storage):
    user = await make_user(client)
    cat = await make_category(client, user)
    expense, presign = await create_with_receipt(client, user, cat)
    confirmed = await client.post(
        f"{API}/expenses/{expense['id']}/receipt/confirm",
        headers=user["headers"], json={"object_key": presign["object_key"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    response = await client.delete(f"{API}/expenses/{expense['id']}", headers=user["headers"])
    assert response.status_code == 204, response.text
    async with SessionFactory() as db:
        cleanup = await db.scalar(select(ReceiptCleanup).where(ReceiptCleanup.object_key == presign["object_key"]))
        assert cleanup is not None
        assert cleanup.completed_at is None
