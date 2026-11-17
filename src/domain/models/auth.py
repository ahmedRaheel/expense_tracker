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



class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    categories: Mapped[list[Category]] = relationship(back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

