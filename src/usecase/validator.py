"""Use-case validation independent of HTTP routing."""
from datetime import date
from decimal import Decimal
from src.usecase.errors import AppError

CURRENCIES = frozenset({"PKR", "AED", "USD", "EUR"})


def currency_code(value: str) -> str:
    value = value.strip().upper()
    if value not in CURRENCIES:
        raise ValueError("Supported currencies: PKR, AED, USD, EUR")
    return value


def validate_expense_filters(*, date_from: date | None, date_to: date | None,
                             min_amount: Decimal | None, max_amount: Decimal | None) -> None:
    if date_from and date_to and date_to < date_from:
        raise AppError(422, "DATE_RANGE_INVALID", "date_to must be after date_from")
    if min_amount is not None and max_amount is not None and max_amount < min_amount:
        raise AppError(422, "AMOUNT_RANGE_INVALID", "max_amount must be >= min_amount")


def require_idempotency_key(key: str) -> None:
    if not key or len(key) > 200:
        raise AppError(422, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required (max 200 characters)")
