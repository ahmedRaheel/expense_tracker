from uuid import UUID
from fastapi import APIRouter
from src.main.ioc.dependencies import ReceiptsDep, UserDep
from src.usecase.dto.receipts import ReceiptUploadURL, ReceiptConfirm, ReceiptDownload

router = APIRouter(prefix="/expenses", tags=["Receipts"])

@router.post("/{expense_id}/receipt/upload-url", response_model=ReceiptUploadURL)
async def upload_url(expense_id: UUID, service: ReceiptsDep, user: UserDep, content_type: str):
    return await service.upload_url(user, expense_id, content_type)

@router.post("/{expense_id}/receipt/confirm", response_model=ReceiptDownload)
async def confirm(expense_id: UUID, payload: ReceiptConfirm, service: ReceiptsDep, user: UserDep):
    return await service.confirm(user, expense_id, payload)

@router.get("/{expense_id}/receipt", response_model=ReceiptDownload)
async def download(expense_id: UUID, service: ReceiptsDep, user: UserDep):
    return await service.download(user, expense_id)
