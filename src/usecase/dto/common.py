"""Shared response-model configuration and currency validator."""
from pydantic import BaseModel, ConfigDict

class DTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)


