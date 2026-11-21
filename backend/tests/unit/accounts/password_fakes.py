"""In-memory fakes of the password ports and of new accounts (ADR-0015, ARCH-27, TEST-05)."""

from dataclasses import dataclass, field

from app.accounts import (
    AccountId,
    LoginName,
    LoginNameTakenError,
    NewInternalAccount,
    OwnAccount,
    Password,
    PasswordHash,
)

_HASH_PREFIX = "hash-of-"


def hash_of(password: str) -> PasswordHash:
    """Return the hash that `FakePasswordHasher` computes for a password."""
    return PasswordHash(_HASH_PREFIX + password)


class FakePasswordHasher:
    """Hash a password into a readable fake hash."""

    async def hash_password(self, password: Password) -> PasswordHash:
        """Return the fake hash of the password."""
        return hash_of(password.value)


@dataclass(slots=True)
class FakePasswordStore:
    """Own accounts and password hashes by account ID."""

    own_accounts: dict[AccountId, OwnAccount] = field(default_factory=dict[AccountId, OwnAccount])
    saved_hashes: dict[AccountId, PasswordHash] = field(
        default_factory=dict[AccountId, PasswordHash]
    )

    async def load_own_account(self, account_id: AccountId) -> OwnAccount | None:
        """Return the own account, if any."""
        return self.own_accounts.get(account_id)

    async def save_password_hash(self, account_id: AccountId, password_hash: PasswordHash) -> None:
        """Keep the new hash."""
        self.saved_hashes[account_id] = password_hash


@dataclass(slots=True)
class FakeNewAccountStore:
    """Login names in use, and the accounts that were inserted."""

    login_names: list[LoginName] = field(default_factory=list[LoginName])
    saved: list[NewInternalAccount] = field(default_factory=list[NewInternalAccount])

    async def load_login_names_with_prefix(self, prefix: str) -> tuple[LoginName, ...]:
        """Return the names in use that start with the prefix."""
        return tuple(name for name in self.login_names if name.startswith(prefix))

    async def save_new(self, account: NewInternalAccount) -> None:
        """Keep the account, or refuse a login name in use as the unique constraint does."""
        if account.account.login_name in self.login_names:
            raise LoginNameTakenError
        self.login_names.append(account.account.login_name)
        self.saved.append(account)
