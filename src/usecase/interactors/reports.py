from src.usecase.interfaces.gateways import ReportPort
from src.usecase.dto.reports import MonthlyReport
from src.usecase.context.identity import CurrentUser

class ReportsInteractor:
    def __init__(self, gateway: ReportPort) -> None:
        self.gateway = gateway

    async def monthly(self, actor: CurrentUser, year: int, month: int) -> MonthlyReport:
        return await self.gateway.monthly(actor, year, month)
