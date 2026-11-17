from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from src.usecase.dto.common import DTO, currency_code


class ExpenseCreate(BaseModel):
    category_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str
    description: str = Field(default="", max_length=500)
    spent_on: date
    _currency = field_validator("currency")(currency_code)


class ExpensePatch(BaseModel):
    category_id: UUID | None = None
    amount: Decimal | None = Field(None, gt=0, max_digits=18, decimal_places=2)
    currency: str | None = None
    description: str | None = Field(None, max_length=500)
    spent_on: date | None = None
    _currency = field_validator("currency")(lambda v: currency_code(v) if v is not None else v)

    @model_validator(mode="after")
    def check_changes(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied")
        for field in ("category_id", "amount", "currency", "spent_on"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ExpenseDTO(DTO):
    id: UUID
    category_id: UUID
    amount: Decimal
    currency: str
    description: str
    spent_on: date
    receipt_key: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class ExpenseResults(BaseModel):
    items: list[ExpenseDTO]
    next_cursor: str | None

