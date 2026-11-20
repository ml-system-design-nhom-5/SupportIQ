"""The ports of accounts: sign-in, sessions, and internal accounts (ARCH-25, ARCH-26).

They follow ADR-0009, statement 9, and ADR-0015. The ports of new passwords are in
`password_ports`.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from app.accounts.domain.admin import InternalAccount, NewInternalAccount
from app.accounts.domain.identity import (
    AccountId,
    DisplayName,
    LoginName,
    Password,
    PasswordHash,
    SessionToken,
)
from app.accounts.domain.sessions import (
    AuthenticatedSession,
    NewSession,
    SessionIdHash,
    StoredSession,
)
from app.accounts.domain.sign_in import LoginNameHash, SignInAccount


class Authenticator(Protocol):
    """Turn what a request carries into a principal (ADR-0009, statement 9).

    Authorization only ever sees the principal, so a production identity provider replaces
    the implementation of this port and nothing else.
    """

    async def authenticate(self, token: SessionToken | None) -> AuthenticatedSession:
        """Load the session of a request.

        Args:
            token: The value of the session cookie, or None when absent.

        Returns:
            The valid session with its principal.

        Raises:
            SessionRequiredError: The session is missing, unknown, expired, or idle.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        ...


class AccountStore(Protocol):
    """Read accounts for sign-in."""

    async def load_for_sign_in(self, login_name: LoginName) -> SignInAccount | None:
        """Load an account and hold it until the transaction ends.

        The hold makes a concurrent role change or deactivation wait for this sign-in, and
        then delete the session that it created (SEC-42).

        Args:
            login_name: The normalized login name.

        Returns:
            The account, or None when the name is unknown.
        """
        ...


class InternalAccountStore(Protocol):
    """Read and change the internal accounts; customer accounts do not exist here (SEC-41)."""

    async def load_internal(self, account_id: AccountId) -> InternalAccount | None:
        """Load an internal account.

        Args:
            account_id: The account, as a request sent it.

        Returns:
            The account, or None for an unknown ID or a customer account.
        """
        ...

    async def count_active_managers(self) -> int:
        """Count the active managers.

        Returns:
            The number of active accounts with the role `manager`.
        """
        ...

    async def save_change(self, account: InternalAccount) -> None:
        """Store the role and the status of an account.

        Args:
            account: The account after the change.
        """
        ...

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
        ...


class NewAccountStore(Protocol):
    """Insert new internal accounts, and tell which login names exist (ADR-0015)."""

    async def load_login_names_with_prefix(self, prefix: str) -> tuple[LoginName, ...]:
        """Load the login names that start with a prefix.

        Login names are unique across every account, so the names of every account count,
        whatever its role or status.

        Args:
            prefix: The start of the names, such as `staff-`.

        Returns:
            The login names, in no particular order.
        """
        ...

    async def save_new(self, account: NewInternalAccount) -> None:
        """Insert a new account with the hash of its password.

        Args:
            account: The account.

        Raises:
            LoginNameTakenError: An account already has its login name.
        """
        ...


class AccountChangeLock(Protocol):
    """Serialize every account change across replicas (backend foundation design)."""

    async def acquire(self) -> None:
        """Wait for the lock, which ends with the transaction.

        Raises:
            DatabaseUnavailableError: The wait exceeded the lock timeout.
        """
        ...


class SessionRevoker(Protocol):
    """Delete the sessions of an account in the transaction of its change (SEC-42)."""

    async def delete_sessions_of(self, account_id: AccountId) -> None:
        """Delete every session of an account.

        Args:
            account_id: The account.
        """
        ...

    async def delete_other_sessions_of(self, account_id: AccountId, kept: SessionIdHash) -> None:
        """Delete every session of an account except one.

        Args:
            account_id: The account.
            kept: The session that stays, the one of the request.
        """
        ...


class SessionStore(Protocol):
    """Keep sessions by the hash of their identifier."""

    async def save(self, session: NewSession) -> None:
        """Store a new session.

        Args:
            session: The session.
        """
        ...

    async def load(self, session_id_hash: SessionIdHash) -> StoredSession | None:
        """Load a session with the current state of its account.

        Args:
            session_id_hash: The hash of the session identifier.

        Returns:
            The session, or None when no session has this hash.
        """
        ...

    async def touch(self, session_id_hash: SessionIdHash, last_seen_at: datetime) -> None:
        """Update when a session was last seen.

        Args:
            session_id_hash: The hash of the session identifier.
            last_seen_at: The current time.
        """
        ...

    async def delete(self, session_id_hash: SessionIdHash) -> None:
        """Delete one session.

        Args:
            session_id_hash: The hash of the session identifier.
        """
        ...

    async def delete_expired(self, *, now: datetime, idle_since: datetime) -> None:
        """Delete sessions past their lifetime or idle, without waiting for locked rows.

        Args:
            now: Sessions with `expires_at` at or before this time are deleted.
            idle_since: Sessions last seen at or before this time are deleted.
        """
        ...


class SignInFailureStore(Protocol):
    """Count failed sign-ins per login name, in PostgreSQL so replicas share them (ARCH-41)."""

    async def count_since(self, login_name_hash: LoginNameHash, since: datetime) -> int:
        """Count the failures of a name after a time.

        Args:
            login_name_hash: The hash of the normalized login name.
            since: Failures at or before this time no longer count.

        Returns:
            The number of failures.
        """
        ...

    async def save_failure(
        self, login_name_hash: LoginNameHash, *, failed_at: datetime, expired_since: datetime
    ) -> None:
        """Record a failure and delete expired failures of every name.

        Args:
            login_name_hash: The hash of the normalized login name.
            failed_at: The current time.
            expired_since: Failures at or before this time are deleted.
        """
        ...

    async def delete_failures(self, login_name_hash: LoginNameHash) -> None:
        """Forget the failures of a name after a successful sign-in.

        Args:
            login_name_hash: The hash of the normalized login name.
        """
        ...


class PasswordVerifier(Protocol):
    """Verify passwords against their hashes, without blocking the event loop."""

    async def verify(self, password_hash: PasswordHash, password: Password) -> bool:
        """Tell whether a password matches a hash.

        Args:
            password_hash: The Argon2id hash.
            password: The password as typed.

        Returns:
            True on a match. A malformed hash matches nothing.
        """
        ...


class SessionTokenGenerator(Protocol):
    """Generate raw session identifiers (ARCH-31)."""

    def generate(self) -> SessionToken:
        """Return a new random session identifier."""
        ...


class StaffDirectory(Protocol):
    """Name the staff and managers who acted on a ticket, for the console (ADR-0012)."""

    async def load_display_names(
        self, account_ids: frozenset[AccountId]
    ) -> Mapping[AccountId, DisplayName]:
        """Load the display names of internal accounts in one query.

        Args:
            account_ids: The accounts.

        Returns:
            The display name of each known internal account. Confidential.
        """
        ...
