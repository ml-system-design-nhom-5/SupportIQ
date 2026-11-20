"""Builders of accounts and sessions (TEST-05)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import insert

from app.accounts import SessionToken, hash_session_token
from app.accounts.adapters.tables import AccountRow, SessionRow
from tests.integration.builders.rows import RowWriter
from tests.unit.platform.fakes import FAKE_CLOCK_START

# Not a real Argon2id hash: rows built with it cannot sign in. Sign-in tests set their own.
UNUSABLE_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$not-a-real-salt$not-a-real-hash"


@dataclass(frozen=True, slots=True)
class AccountSpec:
    """An account to build.

    Attributes:
        role: The role.
        is_active: Whether the account can sign in.
        customer_id: The customer of a customer account.
        display_name: The display name; a name from the role and a number when None.
        password_hash: The Argon2id hash; unusable by default.
        login_name: The login name; the role and a number when None.
    """

    role: str
    is_active: bool = True
    customer_id: UUID | None = None
    display_name: str | None = None
    password_hash: str = UNUSABLE_PASSWORD_HASH
    login_name: str | None = None


class AccountRows:
    """Insert accounts and their sessions."""

    def __init__(self, writer: RowWriter) -> None:
        """Keep the writer that every area shares.

        Args:
            writer: Writes the rows and gives their deterministic values.
        """
        self._writer = writer

    async def account(self, spec: AccountSpec) -> UUID:
        """Insert an account and return its ID; a customer account needs `customer_id`."""
        account_id = self._writer.next_uuid()
        number = self._writer.next_number()
        await self._writer.execute(
            insert(AccountRow).values(
                account_id=account_id,
                login_name=spec.login_name or f"{spec.role}-{number}",
                display_name=spec.display_name or f"{spec.role.title()} {number}",
                role=spec.role,
                is_active=spec.is_active,
                customer_id=spec.customer_id,
                password_hash=spec.password_hash,
                created_at=self._writer.next_time(),
            )
        )
        return account_id

    async def session(
        self, account_id: UUID, role: str, last_seen_at: datetime, expires_at: datetime
    ) -> str:
        """Insert a session of the account and return the raw identifier, for the cookie."""
        token = f"test-session-{self._writer.next_number()}"
        await self._writer.execute(
            insert(SessionRow).values(
                session_id_hash=hash_session_token(SessionToken(token)),
                account_id=account_id,
                role=role,
                created_at=FAKE_CLOCK_START,
                last_seen_at=last_seen_at,
                expires_at=expires_at,
            )
        )
        return token
