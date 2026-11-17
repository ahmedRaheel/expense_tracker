"""Shared response-model configuration and currency validator."""
from pydantic import BaseModel, ConfigDict
from src.usecase.validator import currency_code

class DTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)


