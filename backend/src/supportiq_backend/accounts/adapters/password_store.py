"""Password hashes in PostgreSQL: the own account under its row lock, and new hashes (ADR-0015)."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.accounts.adapters.mapping import to_session_account
from supportiq_backend.accounts.adapters.tables import AccountRow
from supportiq_backend.accounts.domain import AccountId, LoginName, OwnAccount, PasswordHash


class PostgresPasswordStore:
    """Implement the `PasswordStore` port on `accounts`; `supportiq_app` may update the hash."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def load_own_account(self, account_id: AccountId) -> OwnAccount | None:
        """Load the caller's own account with `FOR UPDATE`, held until the transaction ends.

        Args:
            account_id: The account of the session.

        Returns:
            The account, or None when no account has this ID.
        """
        row = await self._session.scalar(
            select(AccountRow).where(AccountRow.account_id == UUID(account_id)).with_for_update()
        )
        if row is None:
            return None
        return OwnAccount(
            account=to_session_account(row),
            login_name=LoginName(row.login_name),
            password_hash=PasswordHash(row.password_hash),
            is_active=row.is_active,
        )

    async def save_password_hash(self, account_id: AccountId, password_hash: PasswordHash) -> None:
        """Store the hash of a new password; the update locks the row until the transaction ends.

        Args:
            account_id: The account.
            password_hash: The Argon2id hash.
        """
        await self._session.execute(
            update(AccountRow)
            .where(AccountRow.account_id == UUID(account_id))
            .values(password_hash=password_hash)
            .execution_options(synchronize_session=False)
        )
