from fastapi import APIRouter, Response
from src.main.ioc.dependencies import AuthDep, UserDep
from src.usecase.dto.auth import RegisterRequest, LoginRequest, RefreshRequest, UserDTO, TokenPair

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=UserDTO, status_code=201)
async def register(payload: RegisterRequest, service: AuthDep):
    return await service.register(payload)

@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, service: AuthDep):
    return await service.login(payload)

@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, service: AuthDep):
    return await service.refresh(payload)

@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, service: AuthDep, user: UserDep):
    await service.logout(payload, user)
    return Response(status_code=204)
