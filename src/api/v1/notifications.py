from fastapi import APIRouter, Query
from src.main.ioc.dependencies import NotificationsDep, UserDep
from src.usecase.dto.notifications import NotificationDTO

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("", response_model=list[NotificationDTO])
async def notifications(service: NotificationsDep, user: UserDep, limit: int = Query(50, ge=1, le=100)):
    return await service.list(user, limit)
