from uuid import UUID
from src.usecase.interfaces.gateways import ReceiptPort
from src.usecase.dto.receipts import ReceiptUploadURL, ReceiptConfirm, ReceiptDownload
from src.usecase.context.identity import CurrentUser

class ReceiptsInteractor:
    def __init__(self, gateway: ReceiptPort) -> None:
        self.gateway = gateway

    async def upload_url(self, actor: CurrentUser, expense_id: UUID, content_type: str) -> ReceiptUploadURL:
        return await self.gateway.upload_url(actor, expense_id, content_type)

    async def confirm(self, actor: CurrentUser, expense_id: UUID, payload: ReceiptConfirm) -> ReceiptDownload:
        return await self.gateway.confirm(actor, expense_id, payload)

    async def download(self, actor: CurrentUser, expense_id: UUID) -> ReceiptDownload:
        return await self.gateway.download(actor, expense_id)
