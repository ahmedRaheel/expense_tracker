"""Composition root. Only this module chooses concrete adapters for application ports."""
from typing import Annotated
from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from src.usecase.errors import AppError
from src.usecase.context.identity import CurrentUser
from src.infrastructure.database.session import get_session
from src.infrastructure.adapters.auth_security import resolve_actor
from src.infrastructure.adapters.auth import SqlAuthenticationAdapter
from src.infrastructure.adapters.gateways import (
    SqlCategoryAdapter, SqlExpenseAdapter, SqlReportAdapter, SqlNotificationAdapter,
)
from src.infrastructure.adapters.imports import SqlImportAdapter
from src.infrastructure.adapters.receipts import SqlReceiptAdapter
from src.usecase.interactors.auth import AuthenticationInteractor
from src.usecase.interactors.categories import CategoryInteractor
from src.usecase.interactors.expenses import ExpenseInteractor
from src.usecase.interactors.reports import ReportsInteractor
from src.usecase.interactors.notifications import NotificationsInteractor
from src.usecase.interactors.imports import ImportsInteractor
from src.usecase.interactors.receipts import ReceiptsInteractor

SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]

def get_redis(request: Request) -> Redis:
    return request.app.state.redis

RedisDep = Annotated[Redis, Depends(get_redis)]
bearer = HTTPBearer(auto_error=False)

async def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(401, "AUTH_REQUIRED", "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    return await resolve_actor(credentials.credentials)

UserDep = Annotated[CurrentUser, Depends(current_user)]


def provide_auth(session: SessionDep, redis: RedisDep) -> AuthenticationInteractor:
    return AuthenticationInteractor(SqlAuthenticationAdapter(session, redis))
AuthDep = Annotated[AuthenticationInteractor, Depends(provide_auth)]


def provide_categories(session: SessionDep) -> CategoryInteractor:
    return CategoryInteractor(SqlCategoryAdapter(session))
CategoriesDep = Annotated[CategoryInteractor, Depends(provide_categories)]


def provide_expenses(session: SessionDep, redis: RedisDep) -> ExpenseInteractor:
    return ExpenseInteractor(SqlExpenseAdapter(session, redis))
ExpensesDep = Annotated[ExpenseInteractor, Depends(provide_expenses)]


def provide_reports(session: SessionDep) -> ReportsInteractor:
    return ReportsInteractor(SqlReportAdapter(session))
ReportsDep = Annotated[ReportsInteractor, Depends(provide_reports)]


def provide_notifications(session: SessionDep) -> NotificationsInteractor:
    return NotificationsInteractor(SqlNotificationAdapter(session))
NotificationsDep = Annotated[NotificationsInteractor, Depends(provide_notifications)]


def provide_imports(session: SessionDep, redis: RedisDep) -> ImportsInteractor:
    return ImportsInteractor(SqlImportAdapter(session, redis))
ImportsDep = Annotated[ImportsInteractor, Depends(provide_imports)]


def provide_receipts(session: SessionDep) -> ReceiptsInteractor:
    return ReceiptsInteractor(SqlReceiptAdapter(session))
ReceiptsDep = Annotated[ReceiptsInteractor, Depends(provide_receipts)]
