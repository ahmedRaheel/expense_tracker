from fastapi import APIRouter, Query
from src.main.ioc.dependencies import ReportsDep, UserDep
from src.usecase.dto.reports import MonthlyReport

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/monthly", response_model=MonthlyReport)
async def monthly_report(service: ReportsDep, user: UserDep, year: int = Query(ge=2000, le=2100),
                         month: int = Query(ge=1, le=12)):
    return await service.monthly(user, year, month)
