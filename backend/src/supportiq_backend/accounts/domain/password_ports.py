"""The ports of new passwords: hashing one, and replacing the hash of an account (ADR-0015).

Account creations, password changes, password resets, and the seed hash a password before any
transaction opens (account management design, Locks).
"""

from typing import Protocol

from supportiq_backend.accounts.domain.identity import AccountId, Password, PasswordHash
from supportiq_backend.accounts.domain.passwords import OwnAccount


class PasswordHasher(Protocol):
    """Hash passwords with a new random salt, without blocking the event loop (ADR-0009)."""

    async def hash_password(self, password: Password) -> PasswordHash:
        """Hash a password exactly as typed.

        Args:
            password: The password.

        Returns:
            The Argon2id hash.
        """
        ...


class PasswordStore(Protocol):
    """Read and replace the password hashes of accounts (ADR-0015)."""

    async def load_own_account(self, account_id: AccountId) -> OwnAccount | None:
        """Load the caller's own account and lock its row until the transaction ends.

        The row lock queues a change behind a reset or another change of the same account and
        blocks no other account (account management design, Locks).

        Args:
            account_id: The account of the session.

        Returns:
            The account, or None when no account has this ID.
        """
        ...

    async def save_password_hash(self, account_id: AccountId, password_hash: PasswordHash) -> None:
        """Store the hash of a new password; the update locks the account's row.

        Args:
            account_id: The account.
            password_hash: The Argon2id hash.
        """
        ...
