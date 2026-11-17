from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from usecase.dto.common import DTO, currency_code


class MonthlyCategoryDTO(BaseModel):
    category_id: UUID
    name: str
    total: Decimal
    previous_total: Decimal
    change_from_last_month: Decimal
    monthly_budget: Decimal | None
    percentage_used: Decimal | None


class MonthlyReport(BaseModel):
    year: int
    month: int
    base_currency: str
    categories: list[MonthlyCategoryDTO]
    grand_total: Decimal

