from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, Numeric, String, Text, UniqueConstraint, func, text as sqltext,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.domain.models.base import Base, uuid_pk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.models.categories import Category


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="positive_amount"),
        ForeignKeyConstraint(["category_id", "user_id"], ["categories.id", "categories.user_id"], ondelete="RESTRICT", name="fk_expense_category_owner"),
        Index("ix_expenses_owner_date_id", "user_id", sqltext("spent_on DESC"), sqltext("id DESC")),
        Index("ix_expenses_category_month", "category_id", "spent_on"),
    )
    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    spent_on: Mapped[date] = mapped_column(Date, nullable=False)
    receipt_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    category: Mapped[Category] = relationship(back_populates="expenses")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_owner_key"),)
    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSONB)
    status_code: Mapped[int] = mapped_column(Integer, default=201)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

