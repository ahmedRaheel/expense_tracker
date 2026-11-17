from src.usecase.interfaces.gateways import AuthenticationPort
from src.usecase.dto.auth import RegisterRequest, LoginRequest, RefreshRequest, TokenPair, UserDTO
from src.usecase.context.identity import CurrentUser

class AuthenticationInteractor:
    def __init__(self, gateway: AuthenticationPort) -> None:
        self.gateway = gateway

    async def register(self, request: RegisterRequest) -> UserDTO:
        return await self.gateway.register(request)

    async def login(self, request: LoginRequest) -> TokenPair:
        return await self.gateway.login(request)

    async def refresh(self, request: RefreshRequest) -> TokenPair:
        return await self.gateway.refresh(request)

    async def logout(self, request: RefreshRequest, actor: CurrentUser) -> None:
        await self.gateway.logout(request, actor)
