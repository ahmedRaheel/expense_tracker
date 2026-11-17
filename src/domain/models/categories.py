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
    from src.domain.models.auth import User
    from src.domain.models.expenses import Expense


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_name", name="uq_categories_owner_name"),
        UniqueConstraint("id", "user_id", name="uq_categories_id_user"),
    )
    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(150), nullable=False)
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    user: Mapped[User] = relationship(back_populates="categories")
    expenses: Mapped[list[Expense]] = relationship(back_populates="category")

