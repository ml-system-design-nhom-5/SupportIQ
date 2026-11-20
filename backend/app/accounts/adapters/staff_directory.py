"""The `StaffDirectory` port on `accounts`: display names of internal accounts only (SEC-41)."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.adapters.tables import AccountRow
from app.accounts.domain import AccountId, DisplayName, Role


class PostgresStaffDirectory:
    """Implement the `StaffDirectory` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the directory to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def load_display_names(
        self, account_ids: frozenset[AccountId]
    ) -> Mapping[AccountId, DisplayName]:
        """Load the display names of internal accounts in one query.

        Args:
            account_ids: The accounts.

        Returns:
            The display name of each known internal account. Customer accounts are left out.
        """
        if not account_ids:
            return {}
        rows = await self._session.execute(
            select(AccountRow.account_id, AccountRow.display_name).where(
                AccountRow.account_id.in_([UUID(account_id) for account_id in account_ids]),
                AccountRow.role != Role.CUSTOMER.value,
            )
        )
        return {AccountId(str(row.account_id)): DisplayName(row.display_name) for row in rows}
