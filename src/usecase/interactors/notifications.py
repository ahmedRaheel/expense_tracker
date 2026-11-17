from src.usecase.interfaces.gateways import NotificationPort
from src.usecase.dto.notifications import NotificationDTO
from src.usecase.context.identity import CurrentUser

class NotificationsInteractor:
    def __init__(self, gateway: NotificationPort) -> None:
        self.gateway = gateway

    async def list(self, actor: CurrentUser, limit: int) -> list[NotificationDTO]:
        return await self.gateway.list(actor, limit)
