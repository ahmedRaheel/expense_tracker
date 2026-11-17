from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from usecase.dto.common import DTO, currency_code


class NotificationDTO(DTO):
    id: UUID
    category_id: UUID
    month: date
    level: int
    message: str
    created_at: datetime

