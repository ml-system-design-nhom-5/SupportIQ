"""ORM model of `audit_log_entries`, used only inside the audit adapters (PY-39, SEC-39)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class AuditTables(DeclarativeBase):
    """The declarative base of the tables that audit owns."""


class AuditLogEntryRow(AuditTables):
    """A row of `audit_log_entries`: insert-only, with Internal data only (SEC-39)."""

    __tablename__ = "audit_log_entries"

    entry_id: Mapped[UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(Text)
    actor_account_id: Mapped[UUID | None]
    ticket_id: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, str | int | bool]] = mapped_column(JSONB)
