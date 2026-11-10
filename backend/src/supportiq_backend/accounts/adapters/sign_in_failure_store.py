"""Sign-in failures in PostgreSQL, so every replica sees the same count (ARCH-41)."""

from datetime import datetime

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.accounts.adapters.tables import SignInFailureRow
from supportiq_backend.accounts.domain import LoginNameHash
from supportiq_backend.platform.persistence import delete_rows_not_held


class PostgresSignInFailureStore:
    """Implement the `SignInFailureStore` port on `sign_in_failures`."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def count_since(self, login_name_hash: LoginNameHash, since: datetime) -> int:
        """Count the failures of a name after a time.

        Args:
            login_name_hash: The hash of the normalized login name.
            since: Failures at or before this time no longer count.

        Returns:
            The number of failures.
        """
        count = await self._session.scalar(
            select(func.count())
            .select_from(SignInFailureRow)
            .where(
                SignInFailureRow.login_name_hash == login_name_hash,
                SignInFailureRow.failed_at > since,
            )
        )
        return count or 0

    async def save_failure(
        self, login_name_hash: LoginNameHash, *, failed_at: datetime, expired_since: datetime
    ) -> None:
        """Record a failure and delete expired failures, skipping rows held by others.

        Args:
            login_name_hash: The hash of the normalized login name.
            failed_at: The current time.
            expired_since: Failures at or before this time are deleted.
        """
        await delete_rows_not_held(
            self._session, SignInFailureRow, SignInFailureRow.failed_at <= expired_since
        )
        await self._session.execute(
            insert(SignInFailureRow).values(login_name_hash=login_name_hash, failed_at=failed_at)
        )

    async def delete_failures(self, login_name_hash: LoginNameHash) -> None:
        """Forget the failures of a name after a successful sign-in.

        Args:
            login_name_hash: The hash of the normalized login name.
        """
        await self._session.execute(
            delete(SignInFailureRow)
            .where(SignInFailureRow.login_name_hash == login_name_hash)
            .execution_options(synchronize_session=False)
        )
