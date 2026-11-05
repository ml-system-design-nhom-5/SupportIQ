"""Application records. Commerce payloads preserve the original synthetic source."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    login_name: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    customer_id: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    avatar_data_url: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)


class SessionRecord(Base):
    __tablename__ = "sessions"
    session_id_hash: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"))
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SignInFailure(Base):
    __tablename__ = "sign_in_failures"
    failure_id: Mapped[str] = mapped_column(String, primary_key=True)
    login_name_hash: Mapped[str] = mapped_column(String, index=True)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Ticket(Base):
    __tablename__ = "tickets"
    ticket_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String, index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.order_id"))
    status: Mapped[str] = mapped_column(String, default="open", index=True)
    handling_mode: Mapped[str] = mapped_column(String, default="assisted")
    is_authority_required: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handling_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_suggestion_id: Mapped[str | None] = mapped_column(String)
    proposal: Mapped[dict | None] = mapped_column(JSON)
    escalation: Mapped[dict | None] = mapped_column(JSON)
    reply: Mapped[dict | None] = mapped_column(JSON)


class CustomerMessage(Base):
    __tablename__ = "customer_messages"
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id"), primary_key=True)
    body: Mapped[str] = mapped_column(Text)


class Suggestion(Base):
    __tablename__ = "suggestions"
    suggestion_id: Mapped[str] = mapped_column(String, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
    request_payload: Mapped[dict] = mapped_column(JSON)
    pseudonym_map: Mapped[dict] = mapped_column(JSON)


class SuggestionJob(Base):
    __tablename__ = "suggestion_jobs"
    suggestion_id: Mapped[str] = mapped_column(ForeignKey("suggestions.suggestion_id"), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    record_id: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEntry(Base):
    __tablename__ = "audit_log_entries"
    entry_id: Mapped[str] = mapped_column(String, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String, index=True)
    actor_account_id: Mapped[str | None] = mapped_column(String)
    ticket_id: Mapped[str | None] = mapped_column(String)
    trace_id: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)
