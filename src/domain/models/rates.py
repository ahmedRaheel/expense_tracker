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


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("currency", "valid_on", name="uq_rates_currency_date"),)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    valid_on: Mapped[date] = mapped_column(Date, primary_key=True)
    rate_to_usd: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)

