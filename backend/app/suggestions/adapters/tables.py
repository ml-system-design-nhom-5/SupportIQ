"""ORM models of the suggestion tables, used only inside the suggestions adapters (PY-39)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# An absent value is SQL `NULL`, never the JSON value `null`: by default SQLAlchemy writes
# Python `None` as JSON `null`, which `IS NULL` does not match.
_NULLABLE_JSONB = JSONB(none_as_null=True)


class SuggestionsTables(DeclarativeBase):
    """The declarative base of the tables that suggestions owns."""


class SuggestionRow(SuggestionsTables):
    """A row of `suggestions`, inserted once; `request` is written once, from absent."""

    __tablename__ = "suggestions"

    suggestion_id: Mapped[UUID] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(Text)
    intent_override: Mapped[str | None] = mapped_column(Text)
    requested_by_account_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[str] = mapped_column(Text)
    request: Mapped[object | None] = mapped_column(_NULLABLE_JSONB)


class SuggestionPartRow(SuggestionsTables):
    """A row of `suggestion_parts`: final once its status leaves `pending`."""

    __tablename__ = "suggestion_parts"

    suggestion_id: Mapped[UUID] = mapped_column(primary_key=True)
    part: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB)
    release_id: Mapped[str | None] = mapped_column(Text)
    versions: Mapped[dict[str, str] | None] = mapped_column(_NULLABLE_JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    llm_input_token_count: Mapped[int | None] = mapped_column(Integer)
    llm_output_token_count: Mapped[int | None] = mapped_column(Integer)
    llm_cost_micro_usd: Mapped[int | None] = mapped_column(Integer)
    mask_count_by_type: Mapped[dict[str, int] | None] = mapped_column(_NULLABLE_JSONB)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[object | None] = mapped_column(_NULLABLE_JSONB)


class SuggestionJobRow(SuggestionsTables):
    """A row of `suggestion_jobs`: one job per suggestion (ADR-0011)."""

    __tablename__ = "suggestion_jobs"

    suggestion_id: Mapped[UUID] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(Text)
    attempt_number: Mapped[int] = mapped_column(Integer)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
