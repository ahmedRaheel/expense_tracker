"""Single object-storage boundary. Async aioboto3; private S3-compatible bucket."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from src.main.config import get_settings
from src.usecase.errors import AppError

from src.infrastructure.adapters.storage_constants import MIME_TO_EXT, MAX_RECEIPT_BYTES


def detect_content_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


class S3Storage:
    def __init__(self):
        self.settings = get_settings()
        self.session = aioboto3.Session()

    @asynccontextmanager
    async def client(self, *, public: bool = False):
        settings = self.settings
        kwargs = {"region_name": settings.storage_region, "config": BotoConfig(signature_version="s3v4")}
        endpoint = settings.storage_public_endpoint_url if public else settings.storage_endpoint_url
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        if settings.storage_access_key and settings.storage_secret_key:
            kwargs["aws_access_key_id"] = settings.storage_access_key
            kwargs["aws_secret_access_key"] = settings.storage_secret_key
        async with self.session.client("s3", **kwargs) as s3:
            yield s3

    async def upload_post(self, key: str, content_type: str):
        async with self.client(public=True) as s3:
            return await s3.generate_presigned_post(
                Bucket=self.settings.storage_bucket, Key=key,
                Fields={"Content-Type": content_type},
                Conditions=[["content-length-range", 1, MAX_RECEIPT_BYTES], {"Content-Type": content_type}],
                ExpiresIn=900,
            )

    async def validate_object(self, key: str, expected_type: str):
        try:
            async with self.client() as s3:
                meta = await s3.head_object(Bucket=self.settings.storage_bucket, Key=key)
                size = int(meta["ContentLength"])
                if size < 1 or size > MAX_RECEIPT_BYTES:
                    raise AppError(422, "RECEIPT_SIZE_INVALID", "Receipt must be between 1 byte and 5 MB")
                response = await s3.get_object(Bucket=self.settings.storage_bucket, Key=key, Range="bytes=0-15")
                try:
                    head = await response["Body"].read(16)
                finally:
                    response["Body"].close()
                detected = detect_content_type(head)
                if detected != expected_type:
                    raise AppError(422, "RECEIPT_TYPE_INVALID", "Receipt content does not match allowed file type")
                return size
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise AppError(422, "RECEIPT_NOT_FOUND", "Uploaded receipt was not found in object storage") from exc
            # Never disguise S3 permission failures or transient outages as missing files.
            raise AppError(502, "STORAGE_UNAVAILABLE", "Unable to verify uploaded receipt") from exc

    async def download_url(self, key: str):
        async with self.client(public=True) as s3:
            return await s3.generate_presigned_url("get_object", Params={"Bucket": self.settings.storage_bucket, "Key": key}, ExpiresIn=900)

    async def delete_object(self, key: str):
        async with self.client() as s3:
            await s3.delete_object(Bucket=self.settings.storage_bucket, Key=key)
