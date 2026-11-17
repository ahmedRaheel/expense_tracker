from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from src.domain.dto.common import DTO, currency_code


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    monthly_budget: Decimal | None = Field(None, gt=0, max_digits=18, decimal_places=2)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str):
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Category name is required")
        return cleaned


class CategoryDTO(DTO):
    id: UUID
    name: str
    monthly_budget: Decimal | None
    current_month_spend: Decimal = Decimal("0.00")
    percentage_used: Decimal | None = None

