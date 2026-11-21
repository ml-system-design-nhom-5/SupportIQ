"""ORM model of the pseudonym map, used only inside the pseudonymization adapters (PY-39)."""

from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PseudonymizationTables(DeclarativeBase):
    """The declarative base of the table that pseudonymization owns."""


class PseudonymMapEntryRow(PseudonymizationTables):
    """A row of `pseudonym_map_entries`: inserted once, never updated (ADR-0010, item 3).

    `original_value` is Confidential, so no code outside this feature reads the table.
    """

    __tablename__ = "pseudonym_map_entries"

    ticket_id: Mapped[str] = mapped_column(Text, primary_key=True)
    pseudonym: Mapped[str] = mapped_column(Text, primary_key=True)
    pseudonym_type: Mapped[str] = mapped_column(Text)
    original_value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
