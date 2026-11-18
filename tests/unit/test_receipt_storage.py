from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError
from src.infrastructure.adapters.s3 import S3Storage, detect_content_type
from src.infrastructure.adapters.storage_constants import MAX_RECEIPT_BYTES
from src.usecase.errors import AppError


@pytest.mark.parametrize(
    ("filename", "first_bytes", "content_type"),
    [
        ("receipt.jpg", b"\xff\xd8\xff\xe0rest", "image/jpeg"),
        ("receipt.png", b"\x89PNG\r\n\x1a\nrest", "image/png"),
        ("receipt.pdf", b"%PDF-1.7\n", "application/pdf"),
        ("malware.png", b"MZ\x90\x00executable", None),
        ("script.pdf", b"#!/bin/sh\nrm -rf /", None),
    ],
)
def test_content_type_comes_from_file_bytes_not_filename(filename, first_bytes, content_type):
    assert detect_content_type(first_bytes) == content_type


class FakeBody:
    def __init__(self, data: bytes):
        self.data = data
        self.closed = False

    async def read(self, length: int) -> bytes:
        return self.data[:length]

    def close(self) -> None:
        self.closed = True


class FakeS3Client:
    def __init__(self, data: bytes = b"\x89PNG\r\n\x1a\nreal-data", size: int | None = None, missing: bool = False):
        self.data, self.size, self.missing = data, size, missing
        self.last_body = None
        self.head_object = AsyncMock(side_effect=self._head)
        self.get_object = AsyncMock(side_effect=self._get)
        self.generate_presigned_post = AsyncMock(return_value={"url": "https://mock.invalid/upload", "fields": {}})
        self.generate_presigned_url = AsyncMock(return_value="https://mock.invalid/download")
        self.delete_object = AsyncMock(return_value={})

    async def _head(self, **kwargs):
        if self.missing:
            raise ClientError({"Error": {"Code": "404", "Message": "Not found"}}, "HeadObject")
        return {"ContentLength": self.size if self.size is not None else len(self.data)}

    async def _get(self, **kwargs):
        self.last_body = FakeBody(self.data)
        return {"Body": self.last_body}


def storage_with_mock_s3(client: FakeS3Client):
    storage = object.__new__(S3Storage)
    storage.settings = SimpleNamespace(storage_bucket="test-bucket")

    @asynccontextmanager
    async def fake_client(*, public: bool = False):
        yield client

    storage.client = fake_client
    return storage


@pytest.mark.asyncio
async def test_storage_accepts_actual_png_and_closes_body():
    s3 = FakeS3Client()
    result = await storage_with_mock_s3(s3).validate_object("receipts/1/valid.png", "image/png")
    assert result == len(s3.data)
    assert s3.last_body.closed
    assert s3.get_object.await_args.kwargs["Range"] == "bytes=0-15"


@pytest.mark.asyncio
async def test_storage_rejects_executable_disguised_as_png():
    s3 = FakeS3Client(data=b"MZ\x90\x00Windows executable bytes")
    with pytest.raises(AppError) as exc:
        await storage_with_mock_s3(s3).validate_object("receipts/1/fake.png", "image/png")
    assert exc.value.code == "RECEIPT_TYPE_INVALID"
    assert s3.last_body.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, MAX_RECEIPT_BYTES + 1])
async def test_storage_rejects_empty_or_oversized_uploads(size):
    s3 = FakeS3Client(size=size)
    with pytest.raises(AppError) as exc:
        await storage_with_mock_s3(s3).validate_object("receipts/1/file.png", "image/png")
    assert exc.value.code == "RECEIPT_SIZE_INVALID"
    s3.get_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_missing_object_is_not_reported_as_valid():
    with pytest.raises(AppError) as exc:
        await storage_with_mock_s3(FakeS3Client(missing=True)).validate_object("missing.png", "image/png")
    assert exc.value.code == "RECEIPT_NOT_FOUND"


@pytest.mark.asyncio
async def test_upload_presign_enforces_content_type_size_and_short_expiry():
    s3 = FakeS3Client()
    await storage_with_mock_s3(s3).upload_post("receipts/a/b/test.png", "image/png")
    kwargs = s3.generate_presigned_post.await_args.kwargs
    assert kwargs["ExpiresIn"] == 900
    assert ["content-length-range", 1, MAX_RECEIPT_BYTES] in kwargs["Conditions"]
    assert {"Content-Type": "image/png"} in kwargs["Conditions"]
    assert kwargs["Key"] == "receipts/a/b/test.png"


@pytest.mark.asyncio
async def test_download_presigned_link_expires_in_fifteen_minutes():
    s3 = FakeS3Client()
    url = await storage_with_mock_s3(s3).download_url("receipts/a/b/test.png")
    assert url.startswith("https://mock.invalid/")
    assert s3.generate_presigned_url.await_args.kwargs["ExpiresIn"] == 900


@pytest.mark.asyncio
async def test_cleanup_deletes_exact_object_key():
    s3 = FakeS3Client()
    await storage_with_mock_s3(s3).delete_object("receipts/a/b/test.png")
    s3.delete_object.assert_awaited_once_with(Bucket="test-bucket", Key="receipts/a/b/test.png")


@pytest.mark.asyncio
async def test_storage_access_denied_is_not_misreported_as_missing():
    s3 = FakeS3Client()

    async def deny(**kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "HeadObject")

    s3.head_object.side_effect = deny
    with pytest.raises(AppError) as exc:
        await storage_with_mock_s3(s3).validate_object("receipts/1/file.png", "image/png")
    assert exc.value.status == 502
    assert exc.value.code == "STORAGE_UNAVAILABLE"
