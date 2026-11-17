from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    email: str
    base_currency: str
    session_version: int
