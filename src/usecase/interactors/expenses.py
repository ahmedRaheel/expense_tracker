from datetime import date
from decimal import Decimal
from uuid import UUID
from src.usecase.interfaces.gateways import ExpensePort
from src.usecase.validator import validate_expense_filters, require_idempotency_key
from src.usecase.dto.expenses import ExpenseCreate, ExpensePatch, ExpenseDTO, ExpenseResults
from src.usecase.context.identity import CurrentUser
from src.domain.value_object.money import Money

class ExpenseInteractor:
    def __init__(self, gateway: ExpensePort) -> None:
        self.gateway = gateway

    async def create(self, actor: CurrentUser, request: ExpenseCreate, key: str) -> tuple[dict, bool]:
        require_idempotency_key(key)
        Money(amount=request.amount, currency=request.currency)  # Domain invariant, independent of HTTP validation
        return await self.gateway.create(actor, request, key)

    async def get(self, actor: CurrentUser, expense_id: UUID) -> ExpenseDTO:
        return await self.gateway.get(actor, expense_id)

    async def list(self, actor: CurrentUser, *, cursor: str | None, limit: int,
                   category_id: UUID | None, date_from: date | None, date_to: date | None,
                   min_amount: Decimal | None, max_amount: Decimal | None, currency: str | None,
                   q: str | None) -> ExpenseResults:
        validate_expense_filters(date_from=date_from, date_to=date_to,
                                 min_amount=min_amount, max_amount=max_amount)
        return await self.gateway.list(actor, cursor=cursor, limit=limit, category_id=category_id,
                                       date_from=date_from, date_to=date_to, min_amount=min_amount,
                                       max_amount=max_amount, currency=currency, q=q)

    async def update(self, actor: CurrentUser, expense_id: UUID, expected_version: int,
                     request: ExpensePatch) -> ExpenseDTO:
        return await self.gateway.update(actor, expense_id, expected_version, request)

    async def delete(self, actor: CurrentUser, expense_id: UUID) -> None:
        await self.gateway.delete(actor, expense_id)
