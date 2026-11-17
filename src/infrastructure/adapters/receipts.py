"""SQLAlchemy metadata + S3 integration behind ReceiptPort."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from src.application.errors import AppError
from src.application.dto.receipts import ReceiptUploadURL, ReceiptDownload
from src.application.interfaces.gateways import StoragePort
from src.infrastructure.database.session import utcnow
from src.domain.models.expenses import Expense
from src.domain.models.receipts import ReceiptUpload, ReceiptCleanup
from src.infrastructure.adapters.expenses import get_expense
from src.infrastructure.adapters.s3 import S3Storage
from src.infrastructure.adapters.storage_constants import MIME_TO_EXT

class SqlReceiptAdapter:
    def __init__(self, session, storage: StoragePort | None = None):
        self.session = session
        self.storage = storage or S3Storage()

    async def upload_url(self, actor, expense_id, content_type):
        await get_expense(self.session, actor, expense_id)
        if content_type not in MIME_TO_EXT:
            raise AppError(422, "RECEIPT_TYPE_INVALID", "Only image/jpeg, image/png, application/pdf")
        key = f"receipts/{actor.id}/{expense_id}/{uuid4()}.{MIME_TO_EXT[content_type]}"
        url = await self.storage.upload_post(key, content_type)
        self.session.add(ReceiptUpload(user_id=actor.id, expense_id=expense_id,
                                       object_key=key, content_type=content_type,
                                       expires_at=utcnow() + timedelta(minutes=15)))
        await self.session.commit()
        return ReceiptUploadURL(method="POST", url=url["url"], fields=url["fields"], object_key=key, expires_in=900)

    async def confirm(self, actor, expense_id, payload):
        expense = await self.session.scalar(select(Expense).where(
            Expense.id == expense_id, Expense.user_id == actor.id).with_for_update())
        if expense is None:
            raise AppError(404, "EXPENSE_NOT_FOUND", "Expense not found")
        claim = await self.session.scalar(select(ReceiptUpload).where(
            ReceiptUpload.user_id == actor.id, ReceiptUpload.expense_id == expense_id,
            ReceiptUpload.object_key == payload.object_key))
        if claim is None or claim.expires_at < utcnow():
            raise AppError(422, "RECEIPT_UPLOAD_INVALID", "Upload intent missing or expired")
        await self.storage.validate_object(claim.object_key, claim.content_type)
        if expense.receipt_key and expense.receipt_key != claim.object_key:
            self.session.add(ReceiptCleanup(object_key=expense.receipt_key))
        expense.receipt_key = claim.object_key
        claim.confirmed = True
        await self.session.commit()
        return ReceiptDownload(url=await self.storage.download_url(expense.receipt_key))

    async def download(self, actor, expense_id):
        expense = await get_expense(self.session, actor, expense_id)
        if not expense.receipt_key:
            raise AppError(404, "RECEIPT_NOT_FOUND", "Expense has no receipt")
        return ReceiptDownload(url=await self.storage.download_url(expense.receipt_key))
