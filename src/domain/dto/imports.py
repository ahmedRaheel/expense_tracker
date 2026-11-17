from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from src.domain.dto.common import DTO, currency_code


class ImportJobDTO(DTO):
    id: UUID
    status: str
    rows_done: int
    rows_failed: int
    total_rows: int
    last_error: str | None
    errors: list[dict] = Field(default_factory=list)
    next_error_cursor: int | None = None

