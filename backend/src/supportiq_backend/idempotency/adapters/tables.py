"""ORM model of `idempotency_records`, used only inside the idempotency adapters (PY-39)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, LargeBinary, SmallInteger, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class IdempotencyTables(DeclarativeBase):
    """The declarative base of the tables that idempotency owns."""


class IdempotencyRecordRow(IdempotencyTables):
    """A row of `idempotency_records` (ERR-15).

    `response_body` is a `json` column. It is mapped as text, so the stored body is the exact
    text of the original response, and a repeated request returns it byte for byte. It is
    Confidential, because a ticket body holds the customer's message.
    """

    __tablename__ = "idempotency_records"

    account_id: Mapped[UUID] = mapped_column(primary_key=True)
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary)
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
