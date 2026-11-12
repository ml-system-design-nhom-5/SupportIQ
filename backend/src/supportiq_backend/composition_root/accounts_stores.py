"""The stores of each use case of accounts, built on the session of one transaction (ARCH-21).

Every store of a use case shares the session, so all its writes commit or roll back together.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.accounts import (
    AccountChangeStores,
    AccountCreationStores,
    OwnPasswordChangeStores,
    PasswordReplacementStores,
    PasswordResetStores,
    SignInStores,
)
from supportiq_backend.accounts.adapters.account_store import PostgresAccountStore
from supportiq_backend.accounts.adapters.internal_accounts import (
    PostgresAccountChangeLock,
    PostgresInternalAccountStore,
    PostgresNewAccountStore,
)
from supportiq_backend.accounts.adapters.password_store import PostgresPasswordStore
from supportiq_backend.accounts.adapters.session_store import PostgresSessionStore
from supportiq_backend.accounts.adapters.sign_in_failure_store import PostgresSignInFailureStore
from supportiq_backend.audit.adapters.audit_log import PostgresAuditLog
from supportiq_backend.idempotency.adapters.idempotency_store import PostgresIdempotencyStore


def build_sign_in_stores(session: AsyncSession) -> SignInStores:
    """Build the stores of sign-in on one session.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return SignInStores(
        accounts=PostgresAccountStore(session),
        sessions=PostgresSessionStore(session),
        failures=PostgresSignInFailureStore(session),
    )


def build_account_change_stores(session: AsyncSession) -> AccountChangeStores:
    """Build the stores of an account change on one session, so all commit together.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return AccountChangeStores(
        lock=PostgresAccountChangeLock(session),
        accounts=PostgresInternalAccountStore(session),
        sessions=PostgresSessionStore(session),
        audit_log=PostgresAuditLog(session),
        idempotency=PostgresIdempotencyStore(session),
    )


def build_account_creation_stores(session: AsyncSession) -> AccountCreationStores:
    """Build the stores of an account creation on one session, so all commit together.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return AccountCreationStores(
        lock=PostgresAccountChangeLock(session),
        accounts=PostgresInternalAccountStore(session),
        new_accounts=PostgresNewAccountStore(session),
        audit_log=PostgresAuditLog(session),
        idempotency=PostgresIdempotencyStore(session),
    )


def build_own_password_change_stores(session: AsyncSession) -> OwnPasswordChangeStores:
    """Build the stores of an own password change on one session, so all commit together.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return OwnPasswordChangeStores(
        idempotency=PostgresIdempotencyStore(session),
        replacement=_build_password_replacement_stores(session),
    )


def build_password_reset_stores(session: AsyncSession) -> PasswordResetStores:
    """Build the stores of a password reset on one session, so all commit together.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return PasswordResetStores(
        lock=PostgresAccountChangeLock(session),
        accounts=PostgresInternalAccountStore(session),
        idempotency=PostgresIdempotencyStore(session),
        replacement=_build_password_replacement_stores(session),
    )


def _build_password_replacement_stores(session: AsyncSession) -> PasswordReplacementStores:
    return PasswordReplacementStores(
        passwords=PostgresPasswordStore(session),
        sessions=PostgresSessionStore(session),
        failures=PostgresSignInFailureStore(session),
        audit_log=PostgresAuditLog(session),
    )
