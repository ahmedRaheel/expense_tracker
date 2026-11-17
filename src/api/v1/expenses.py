"""Endpoint headers, status codes, and filter parsing; application layer executes use cases."""
from datetime import date
from decimal import Decimal
from uuid import UUID
import re
from fastapi import APIRouter, Header, Query, Response
from fastapi.responses import JSONResponse
from src.usecase.errors import AppError
from src.usecase.dto.expenses import ExpenseCreate, ExpenseDTO, ExpensePatch, ExpenseResults
from src.usecase.validator import currency_code
from src.main.ioc.dependencies import ExpensesDep, UserDep

router = APIRouter(prefix="/expenses", tags=["Expenses"])

@router.post("", status_code=201, response_model=ExpenseDTO)
async def create(payload: ExpenseCreate, service: ExpensesDep, user: UserDep,
                 idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    record, replay = await service.create(user, payload, idempotency_key or "")
    return JSONResponse(status_code=201, content=record,
                        headers={"Idempotency-Replayed": "true" if replay else "false",
                                 "ETag": f'"v{record["version"]}"'})

@router.get("", response_model=ExpenseResults)
async def list_expenses(
    service: ExpensesDep, user: UserDep, cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100), category_id: UUID | None = None,
    date_from: date | None = None, date_to: date | None = None,
    min_amount: Decimal | None = Query(None, ge=0), max_amount: Decimal | None = Query(None, ge=0),
    currency: str | None = None, q: str | None = Query(None, max_length=200),
):
    return await service.list(user, cursor=cursor, limit=limit, category_id=category_id,
                              date_from=date_from, date_to=date_to, min_amount=min_amount,
                              max_amount=max_amount, currency=currency_code(currency) if currency else None, q=q)

@router.get("/{expense_id}", response_model=ExpenseDTO)
async def get_one(expense_id: UUID, service: ExpensesDep, user: UserDep, response: Response):
    result = await service.get(user, expense_id)
    response.headers["ETag"] = f'"v{result.version}"'
    return result

@router.patch("/{expense_id}", response_model=ExpenseDTO)
async def patch(expense_id: UUID, payload: ExpensePatch, service: ExpensesDep, user: UserDep,
                response: Response, if_match: str | None = Header(None, alias="If-Match")):
    if if_match is None:
        raise AppError(428, "PRECONDITION_REQUIRED", "If-Match header is required")
    if not re.fullmatch(r'"v[1-9][0-9]*"', if_match):
        raise AppError(400, "INVALID_ETAG", 'Expected If-Match: "v1"')
    view = await service.update(user, expense_id, int(if_match[2:-1]), payload)
    response.headers["ETag"] = f'"v{view.version}"'
    return view

@router.delete("/{expense_id}", status_code=204)
async def remove(expense_id: UUID, service: ExpensesDep, user: UserDep):
    await service.delete(user, expense_id)
    return Response(status_code=204)
