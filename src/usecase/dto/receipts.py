from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from src.usecase.dto.common import DTO, currency_code


class ReceiptUploadURL(BaseModel):
    method: str
    url: str
    fields: dict[str, str]
    object_key: str
    expires_in: int
    max_bytes: int = 5 * 1024 * 1024


class ReceiptConfirm(BaseModel):
    object_key: str = Field(min_length=10)


class ReceiptDownload(BaseModel):
    url: str
    expires_in: int = 900

