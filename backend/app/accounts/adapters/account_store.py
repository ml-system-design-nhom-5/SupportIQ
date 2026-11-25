"""Accounts in PostgreSQL, read for sign-in (ADR-0009)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.adapters.mapping import to_session_account
from app.accounts.adapters.tables import AccountRow
from app.accounts.domain import LoginName, PasswordHash, SignInAccount
from app.platform import is_storable_text


class PostgresAccountStore:
    """Implement the `AccountStore` port on `accounts`."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def load_for_sign_in(self, login_name: LoginName) -> SignInAccount | None:
        """Load an account with a shared row lock until the transaction ends.

        Args:
            login_name: The normalized login name.

        Returns:
            The account, or None when the name is unknown.

        Raises:
            UnexpectedFailureError: A stored role is no value of its enum: a defect.
        """
        if not is_storable_text(login_name):
            return None
        row = await self._session.scalar(
            select(AccountRow).where(AccountRow.login_name == login_name).with_for_update(read=True)
        )
        if row is None:
            return None
        return SignInAccount(
            account=to_session_account(row),
            is_active=row.is_active,
            password_hash=PasswordHash(row.password_hash),
        )
