from dataclasses import dataclass
from decimal import Decimal
from src.domain.exceptions import DomainError

@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise DomainError("Monetary amounts must be Decimal, never float")
        if not self.amount.is_finite() or self.amount <= 0:
            raise DomainError("Amount must be positive and finite")
        if self.amount.as_tuple().exponent < -2:
            raise DomainError("Amount must not have more than two decimal places")
        if len(self.currency) != 3 or not self.currency.isupper():
            raise DomainError("Currency must be a three-letter uppercase code")
