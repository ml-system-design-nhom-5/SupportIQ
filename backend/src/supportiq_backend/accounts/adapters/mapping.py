"""Mapping from rows of the accounts tables to domain objects (PY-39)."""

from supportiq_backend.accounts.adapters.tables import AccountRow
from supportiq_backend.accounts.domain import (
    AccountId,
    CustomerId,
    DisplayName,
    Role,
    SessionAccount,
)


def to_session_account(row: AccountRow) -> SessionAccount:
    """Map an account row to the account of a session.

    Args:
        row: The row.

    Returns:
        The domain object.
    """
    return SessionAccount(
        account_id=AccountId(str(row.account_id)),
        role=Role(row.role),
        display_name=DisplayName(row.display_name),
        customer_id=None if row.customer_id is None else CustomerId(str(row.customer_id)),
    )
