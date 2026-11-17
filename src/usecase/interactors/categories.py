from src.usecase.interfaces.gateways import CategoryPort
from src.usecase.dto.categories import CategoryCreate, CategoryDTO
from src.usecase.context.identity import CurrentUser

class CategoryInteractor:
    def __init__(self, gateway: CategoryPort) -> None:
        self.gateway = gateway

    async def create(self, actor: CurrentUser, request: CategoryCreate) -> CategoryDTO:
        return await self.gateway.create(actor, request)

    async def list(self, actor: CurrentUser) -> list[CategoryDTO]:
        return await self.gateway.list(actor)
