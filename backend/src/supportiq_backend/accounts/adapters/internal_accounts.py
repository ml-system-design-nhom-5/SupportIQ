"""Internal accounts in PostgreSQL, and the advisory lock of account changes (ADR-0012)."""

from uuid import UUID

from sqlalchemy import and_, collate, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.accounts.adapters.tables import AccountRow
from supportiq_backend.accounts.domain import (
    AccountId,
    DisplayName,
    InternalAccount,
    InternalRole,
    LoginName,
    LoginNameTakenError,
    NewInternalAccount,
)
from supportiq_backend.platform.persistence import BYTE_ORDER_COLLATION, parse_stored_enum

# The key of the transaction-level advisory lock that serializes every account change across
# replicas. Any fixed number works; this one spells "ACCT" in ASCII.
ACCOUNT_CHANGES_LOCK_KEY = 0x41434354
_INTERNAL_ROLES = tuple(role.value for role in InternalRole)


class PostgresInternalAccountStore:
    """Implement the `InternalAccountStore` port; every query excludes customer accounts."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def load_internal(self, account_id: AccountId) -> InternalAccount | None:
        """Load an internal account.

        Args:
            account_id: The account, as a request sent it.

        Returns:
            The account, or None for an ID that is no UUID, an unknown ID, or a customer.
        """
        identifier = _parse_uuid(account_id)
        if identifier is None:
            return None
        row = await self._session.scalar(
            select(AccountRow).where(
                AccountRow.account_id == identifier, AccountRow.role.in_(_INTERNAL_ROLES)
            )
        )
        return None if row is None else _to_internal_account(row)

    async def count_active_managers(self) -> int:
        """Count the active managers.

        Returns:
            The number of active accounts with the role `manager`.
        """
        count = await self._session.scalar(
            select(func.count())
            .select_from(AccountRow)
            .where(AccountRow.role == InternalRole.MANAGER.value, AccountRow.is_active)
        )
        return count or 0

    async def save_change(self, account: InternalAccount) -> None:
        """Store the role and the status of an account.

        Args:
            account: The account after the change.
        """
        await self._session.execute(
            update(AccountRow)
            .where(AccountRow.account_id == UUID(account.account_id))
            .values(role=account.role.value, is_active=account.is_active)
            .execution_options(synchronize_session=False)
        )

    async def load_page(
        self, after: InternalAccount | None, limit: int
    ) -> tuple[InternalAccount, ...]:
        """Load accounts by display name, then account ID, by code point.

        Args:
            after: The account before the page, or None for the first page.
            limit: The maximum number of accounts.

        Returns:
            The accounts of the page.
        """
        name = collate(AccountRow.display_name, BYTE_ORDER_COLLATION)
        statement = (
            select(AccountRow)
            .where(AccountRow.role.in_(_INTERNAL_ROLES))
            .order_by(name, AccountRow.account_id)
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    name > after.display_name,
                    and_(
                        AccountRow.display_name == after.display_name,
                        AccountRow.account_id > UUID(after.account_id),
                    ),
                )
            )
        rows = await self._session.scalars(statement)
        return tuple(_to_internal_account(row) for row in rows)


class PostgresNewAccountStore:
    """Implement the `NewAccountStore` port on `accounts`.

    `supportiq_app` may insert every column except `customer_id`, and a trigger refuses an
    `admin` row from any role but the owner, so only `staff` and `manager` accounts reach the
    table through it (migration `r0002`).
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def load_login_names_with_prefix(self, prefix: str) -> tuple[LoginName, ...]:
        """Load the login names of every account that start with a prefix.

        Args:
            prefix: The start of the names, such as `staff-`.

        Returns:
            The login names.
        """
        names = await self._session.scalars(
            select(AccountRow.login_name).where(
                AccountRow.login_name.startswith(prefix, autoescape=True)
            )
        )
        return tuple(LoginName(name) for name in names)

    async def save_new(self, account: NewInternalAccount) -> None:
        """Insert an account; the unique login name is the second line of defense.

        A concurrent insert of the same name waits for the other transaction, as the
        idempotency records do, so a name that it commits is found taken here.

        Args:
            account: The account.

        Raises:
            LoginNameTakenError: An account already has its login name.
        """
        inserted = await self._session.scalar(
            insert(AccountRow)
            .values(
                account_id=UUID(account.account.account_id),
                login_name=account.account.login_name,
                display_name=account.account.display_name,
                role=account.account.role.value,
                is_active=account.account.is_active,
                password_hash=account.password_hash,
                created_at=account.created_at,
            )
            .on_conflict_do_nothing(index_elements=(AccountRow.login_name,))
            .returning(AccountRow.account_id)
        )
        if inserted is None:
            raise LoginNameTakenError


class PostgresAccountChangeLock:
    """Implement the `AccountChangeLock` port with a transaction-level advisory lock."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the lock to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def acquire(self) -> None:
        """Wait for the lock, at most `lock_timeout`; it ends with the transaction."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_CHANGES_LOCK_KEY}
        )


def _to_internal_account(row: AccountRow) -> InternalAccount:
    return InternalAccount(
        account_id=AccountId(str(row.account_id)),
        login_name=LoginName(row.login_name),
        display_name=DisplayName(row.display_name),
        # The queries select only the internal roles, so this parse never fails.
        role=parse_stored_enum(InternalRole, row.role),
        is_active=row.is_active,
    )


def _parse_uuid(account_id: str) -> UUID | None:
    try:
        return UUID(account_id)
    except ValueError:
        return None
