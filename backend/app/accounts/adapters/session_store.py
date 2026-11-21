"""Sessions in PostgreSQL, by the hash of their identifier (ADR-0009, ARCH-41)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.adapters.mapping import to_session_account
from app.accounts.adapters.tables import AccountRow, SessionRow
from app.accounts.domain import (
    AccountId,
    NewSession,
    Role,
    SessionIdHash,
    StoredSession,
)
from app.platform.persistence import delete_rows_not_held, parse_stored_enum


class PostgresSessionStore:
    """Implement the `SessionStore` port on `sessions`."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def save(self, session: NewSession) -> None:
        """Store a new session; only the hash of its identifier reaches the database.

        Args:
            session: The session.
        """
        await self._session.execute(
            insert(SessionRow).values(
                session_id_hash=session.session_id_hash,
                account_id=UUID(session.account_id),
                role=session.role.value,
                created_at=session.created_at,
                last_seen_at=session.created_at,
                expires_at=session.expires_at,
            )
        )

    async def load(self, session_id_hash: SessionIdHash) -> StoredSession | None:
        """Load a session with the current state of its account.

        Args:
            session_id_hash: The hash of the session identifier.

        Returns:
            The session, or None when no session has this hash.

        Raises:
            UnexpectedFailureError: A stored role is no value of its enum: a defect.
        """
        row = (
            await self._session.execute(
                select(SessionRow, AccountRow)
                .join(AccountRow, AccountRow.account_id == SessionRow.account_id)
                .where(SessionRow.session_id_hash == session_id_hash)
            )
        ).one_or_none()
        if row is None:
            return None
        session_row, account_row = row
        return StoredSession(
            session_id_hash=session_id_hash,
            account=to_session_account(account_row),
            role_at_creation=parse_stored_enum(Role, session_row.role),
            is_account_active=account_row.is_active,
            last_seen_at=session_row.last_seen_at,
            expires_at=session_row.expires_at,
        )

    async def touch(self, session_id_hash: SessionIdHash, last_seen_at: datetime) -> None:
        """Update when a session was last seen.

        Args:
            session_id_hash: The hash of the session identifier.
            last_seen_at: The current time.
        """
        await self._session.execute(
            update(SessionRow)
            .where(SessionRow.session_id_hash == session_id_hash)
            .values(last_seen_at=last_seen_at)
            .execution_options(synchronize_session=False)
        )

    async def delete(self, session_id_hash: SessionIdHash) -> None:
        """Delete one session.

        Args:
            session_id_hash: The hash of the session identifier.
        """
        await self._session.execute(
            delete(SessionRow)
            .where(SessionRow.session_id_hash == session_id_hash)
            .execution_options(synchronize_session=False)
        )

    async def delete_sessions_of(self, account_id: AccountId) -> None:
        """Delete every session of an account, in the transaction of its change (SEC-42).

        Args:
            account_id: The account.
        """
        await self._session.execute(
            delete(SessionRow)
            .where(SessionRow.account_id == UUID(account_id))
            .execution_options(synchronize_session=False)
        )

    async def delete_other_sessions_of(self, account_id: AccountId, kept: SessionIdHash) -> None:
        """Delete every session of an account but one, in the transaction of its change (SEC-42).

        Args:
            account_id: The account.
            kept: The session that stays, the one of the request.
        """
        await self._session.execute(
            delete(SessionRow)
            .where(SessionRow.account_id == UUID(account_id), SessionRow.session_id_hash != kept)
            .execution_options(synchronize_session=False)
        )

    async def delete_expired(self, *, now: datetime, idle_since: datetime) -> None:
        """Delete ended sessions; rows that another transaction holds are left for later.

        Args:
            now: Sessions with `expires_at` at or before this time are deleted.
            idle_since: Sessions last seen at or before this time are deleted.
        """
        await delete_rows_not_held(
            self._session,
            SessionRow,
            or_(SessionRow.expires_at <= now, SessionRow.last_seen_at <= idle_since),
        )
