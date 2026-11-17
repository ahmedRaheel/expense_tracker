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


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (UniqueConstraint("user_id", "sha256", name="uq_import_owner_hash"),)
    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    spool_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    rows_done: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportErrorRow(Base):
    __tablename__ = "import_errors"
    __table_args__ = (UniqueConstraint("job_id", "row_number", name="uq_import_error_row"),)
    id: Mapped[UUID] = uuid_pk()
    job_id: Mapped[UUID] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)

