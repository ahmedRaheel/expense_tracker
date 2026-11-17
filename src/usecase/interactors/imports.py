from uuid import UUID
from src.usecase.interfaces.gateways import ImportPort, AsyncUpload
from src.usecase.dto.imports import ImportJobDTO
from src.usecase.context.identity import CurrentUser

class ImportsInteractor:
    def __init__(self, gateway: ImportPort) -> None:
        self.gateway = gateway

    async def submit(self, actor: CurrentUser, file: AsyncUpload) -> ImportJobDTO:
        return await self.gateway.submit(actor, file)

    async def status(self, actor: CurrentUser, job_id: UUID, error_after: int, error_limit: int) -> ImportJobDTO:
        return await self.gateway.status(actor, job_id, error_after, error_limit)
