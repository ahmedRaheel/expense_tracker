"""Business policy and input validation tests; independent of HTTP/DB services."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.exceptions import DomainError
from src.domain.policies.budget import crossed_thresholds
from src.domain.value_object.money import Money
from src.usecase.dto.expenses import ExpenseCreate, ExpensePatch
from src.usecase.errors import AppError
from src.usecase.validator import (
    currency_code,
    require_idempotency_key,
    validate_expense_filters,
)


@pytest.mark.parametrize("invalid", [Decimal("0"), Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")])
def test_money_rejects_non_positive_or_non_finite(invalid):
    with pytest.raises(DomainError):
        Money(invalid, "PKR")


@pytest.mark.parametrize("invalid", ["pkr", "PK", "USDD"])
def test_money_value_object_rejects_noncanonical_currency(invalid):
    with pytest.raises(DomainError):
        Money(Decimal("1.00"), invalid)


@pytest.mark.parametrize("amount", ["0", "-0.01", "1.001"])
def test_expense_create_validates_money_precision_and_sign(amount):
    with pytest.raises(ValidationError):
        ExpenseCreate(category_id=uuid4(), amount=amount, currency="PKR", spent_on=date.today())


def test_expense_patch_rejects_empty_body():
    with pytest.raises(ValidationError):
        ExpensePatch()


def test_expense_patch_rejects_null_amount():
    with pytest.raises(ValidationError):
        ExpensePatch(amount=None)


@pytest.mark.parametrize("key", ["", "x" * 201])
def test_idempotency_key_is_required_and_bounded(key):
    with pytest.raises(AppError) as exc:
        require_idempotency_key(key)
    assert exc.value.status == 422


def test_valid_idempotency_key_accepted():
    require_idempotency_key("bd91c377-54fa-4e91-9494-f8aba5a43cbe")


def test_filter_validates_date_order():
    with pytest.raises(AppError) as exc:
        validate_expense_filters(
            date_from=date(2026, 11, 20), date_to=date(2026, 11, 15),
            min_amount=None, max_amount=None,
        )
    assert exc.value.code == "DATE_RANGE_INVALID"


def test_filter_allows_equal_min_and_max():
    validate_expense_filters(
        date_from=None, date_to=None,
        min_amount=Decimal("10.00"), max_amount=Decimal("10.00"),
    )


def test_budget_crossing_exactly_eighty_percent():
    assert [x.level for x in crossed_thresholds(
        Decimal("100.00"), Decimal("79.99"), Decimal("80.00")
    )] == [80]


def test_budget_crossing_exactly_one_hundred_percent():
    assert [x.level for x in crossed_thresholds(
        Decimal("100.00"), Decimal("99.99"), Decimal("100.00")
    )] == [100]


def test_currency_normalizes_supported_codes():
    assert currency_code(" aed ") == "AED"
