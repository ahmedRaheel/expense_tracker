"""Pure application/domain tests: no PostgreSQL, Redis, FastAPI or S3 needed."""
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.usecase.dto.expenses import ExpenseCreate
from src.usecase.errors import AppError
from src.usecase.interactors.expenses import ExpenseInteractor
from src.usecase.interactors.categories import CategoryInteractor
from src.usecase.validator import currency_code
from src.usecase.context.identity import Actor
from src.domain.policies.budget import crossed_thresholds
from src.domain.value_object.money import Money
from src.domain.exceptions import DomainError


def make_current_user():
    return Actor(id=uuid4(), email="someone@example.com", base_currency="PKR", session_version=1)


def test_actor_is_immutable():
    actor = make_current_user()
    with pytest.raises(FrozenInstanceError):
        actor.email = "other@example.com"


def test_budget_crosses_both_thresholds():
    events = crossed_thresholds(Decimal("100.00"), Decimal("79.00"), Decimal("110.00"))
    assert [e.level for e in events] == [80, 100]


def test_budget_crosses_only_eighty():
    events = crossed_thresholds(Decimal("100.00"), Decimal("79.00"), Decimal("90.00"))
    assert [e.level for e in events] == [80]


def test_budget_no_repeat_alert_above_threshold():
    assert crossed_thresholds(Decimal("100"), Decimal("101"), Decimal("102")) == ()


def test_budget_no_alert_on_downward_crossing():
    assert crossed_thresholds(Decimal("100"), Decimal("105"), Decimal("70")) == ()


def test_budget_unset():
    assert crossed_thresholds(None, Decimal("0"), Decimal("100")) == ()


@pytest.mark.parametrize("value,expected", [(" pkr ", "PKR"), ("usd", "USD"), ("EUR", "EUR")])
def test_currency_is_normalized(value, expected):
    assert currency_code(value) == expected


def test_invalid_currency_rejected():
    with pytest.raises(ValueError):
        currency_code("BTC")


def test_expense_cannot_have_three_decimal_places():
    with pytest.raises(ValidationError):
        ExpenseCreate(category_id=uuid4(), amount="12.345", currency="USD", spent_on=date.today())


class FakeExpenses:
    def __init__(self):
        self.calls = []

    async def create(self, actor, payload, key):
        self.calls.append((actor, payload, key))
        return {"id": "fake", "version": 1}, False

    async def list(self, actor, **kwargs):
        self.calls.append((actor, kwargs))
        return {"items": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_expense_interactor_calls_port_without_sqlalchemy():
    fake, actor = FakeExpenses(), make_current_user()
    payload = ExpenseCreate(category_id=uuid4(), amount=Decimal("10.00"), currency="PKR", spent_on=date.today())
    result, replay = await ExpenseInteractor(fake).create(actor, payload, "idempotency-1")
    assert not replay and result["version"] == 1
    assert fake.calls[0][0] == actor
    assert fake.calls[0][2] == "idempotency-1"


@pytest.mark.asyncio
async def test_expense_interactor_requires_idempotency_key():
    fake = FakeExpenses()
    payload = ExpenseCreate(category_id=uuid4(), amount="10.00", currency="PKR", spent_on=date.today())
    with pytest.raises(AppError) as ex:
        await ExpenseInteractor(fake).create(make_current_user(), payload, "")
    assert ex.value.status == 422 and not fake.calls


@pytest.mark.asyncio
async def test_expense_interactor_rejects_inverted_amount_filters():
    fake = FakeExpenses()
    with pytest.raises(AppError) as ex:
        await ExpenseInteractor(fake).list(make_current_user(), cursor=None, limit=20, category_id=None,
                                          date_from=None, date_to=None, min_amount=Decimal("30"),
                                          max_amount=Decimal("10"), currency=None, q=None)
    assert ex.value.code == "AMOUNT_RANGE_INVALID" and not fake.calls


def test_money_value_object_uses_decimal_only():
    assert Money(Decimal("10.50"), "PKR").amount == Decimal("10.50")
    with pytest.raises(DomainError):
        Money(10.5, "PKR")

def test_money_value_object_rejects_fractional_overprecision():
    with pytest.raises(DomainError):
        Money(Decimal("10.123"), "USD")
