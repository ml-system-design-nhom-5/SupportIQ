"""Mapping from rows of the accounts tables to domain objects (PY-39)."""

from supportiq_backend.accounts.adapters.tables import AccountRow
from supportiq_backend.accounts.domain import (
    AccountId,
    CustomerId,
    DisplayName,
    Role,
    SessionAccount,
)
from supportiq_backend.platform.persistence import parse_stored_enum


def to_session_account(row: AccountRow) -> SessionAccount:
    """Map an account row to the account of a session.

    Args:
        row: The row.

    Returns:
        The domain object.

    Raises:
        UnexpectedFailureError: The stored role is no value of its enum: a defect.
    """
    return SessionAccount(
        account_id=AccountId(str(row.account_id)),
        role=parse_stored_enum(Role, row.role),
        display_name=DisplayName(row.display_name),
        customer_id=None if row.customer_id is None else CustomerId(str(row.customer_id)),
    )
