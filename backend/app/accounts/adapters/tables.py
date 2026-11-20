"""ORM models of the tables of accounts, used only inside its adapters (PY-39).

The models have no relationships, so no attribute access can start a lazy load in async code.
Repositories map rows to domain objects and never return a row. The data class of each column
follows the backend foundation design.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, LargeBinary, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class AccountsTables(DeclarativeBase):
    """The declarative base of the tables that accounts owns."""


class AccountRow(AccountsTables):
    """A row of `accounts`. Display names and password hashes are Confidential."""

    __tablename__ = "accounts"

    account_id: Mapped[UUID] = mapped_column(primary_key=True)
    login_name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool]
    customer_id: Mapped[UUID | None]
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionRow(AccountsTables):
    """A row of `sessions`: the SHA-256 hash of a session identifier, never the identifier."""

    __tablename__ = "sessions"

    session_id_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    account_id: Mapped[UUID]
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SignInFailureRow(AccountsTables):
    """A row of `sign_in_failures`, keyed by the hash of the typed login name.

    The table has no primary key. The ORM needs an identity, so both columns form one here;
    the migration, not this model, defines the table.
    """

    __tablename__ = "sign_in_failures"

    login_name_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
