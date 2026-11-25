"""The rules of sessions: hashing, idle and absolute expiry, and touches (ADR-0009)."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import NewType

from app.accounts.domain.identity import (
    AccountId,
    CustomerId,
    CustomerPrincipal,
    DisplayName,
    InternalPrincipal,
    InternalRole,
    Principal,
    Role,
    SessionToken,
)

# The SHA-256 of a session identifier, the only form that is stored. Confidential.
SessionIdHash = NewType("SessionIdHash", bytes)


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """How long sessions live, from the settings (ADR-0009, statement 6).

    Attributes:
        idle_timeout: A session unused for this long has expired.
        absolute_lifetime: A session older than this has expired, however busy.
        touch_interval: `last_seen_at` is updated at most this often, so reads do not write
            on every request.
    """

    idle_timeout: timedelta
    absolute_lifetime: timedelta
    touch_interval: timedelta


@dataclass(frozen=True, slots=True)
class SessionAccount:
    """The account of a session, as `SessionView` shows it.

    Attributes:
        account_id: The account.
        role: Its role.
        display_name: The name shown for it. Confidential.
        customer_id: The customer of a customer account; absent otherwise.
    """

    account_id: AccountId
    role: Role
    display_name: DisplayName = field(repr=False)
    customer_id: CustomerId | None = None


@dataclass(frozen=True, slots=True)
class NewSession:
    """A session to store.

    Attributes:
        session_id_hash: The hash of its identifier.
        account_id: The account.
        role: The role of the account at creation.
        created_at: When it was created.
        expires_at: When its absolute lifetime ends.
    """

    session_id_hash: SessionIdHash = field(repr=False)
    account_id: AccountId
    role: Role
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StoredSession:
    """A stored session with the current state of its account.

    Attributes:
        session_id_hash: The hash of its identifier.
        account: The account as it is now.
        role_at_creation: The role when the session was created.
        is_account_active: Whether the account can still sign in.
        last_seen_at: The last touch.
        expires_at: When its absolute lifetime ends.
    """

    session_id_hash: SessionIdHash = field(repr=False)
    account: SessionAccount
    role_at_creation: Role
    is_account_active: bool
    last_seen_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    """A valid session, as every operation that needs one receives it.

    Attributes:
        session_id_hash: The hash of its identifier, for sign-out.
        principal: Who is calling.
        account: The account, for `getCurrentSession`.
    """

    session_id_hash: SessionIdHash = field(repr=False)
    principal: Principal
    account: SessionAccount


def hash_session_token(token: SessionToken) -> SessionIdHash:
    """Compute the stored form of a session identifier.

    Args:
        token: The raw identifier.

    Returns:
        Its SHA-256 hash.
    """
    return SessionIdHash(hashlib.sha256(token.value.encode()).digest())


def build_new_session(
    session_id_hash: SessionIdHash, account: SessionAccount, now: datetime, policy: SessionPolicy
) -> NewSession:
    """Build the session of a successful sign-in.

    Args:
        session_id_hash: The hash of its identifier.
        account: The account that signed in.
        now: The current time.
        policy: The session policy.

    Returns:
        The session, ending after the absolute lifetime.
    """
    return NewSession(
        session_id_hash=session_id_hash,
        account_id=account.account_id,
        role=account.role,
        created_at=now,
        expires_at=now + policy.absolute_lifetime,
    )


def is_session_valid(session: StoredSession, now: datetime, policy: SessionPolicy) -> bool:
    """Tell whether a stored session can still serve requests.

    A session ends at `expires_at` and after `idle_timeout` without a touch, both inclusive.
    A role change or a deactivation deletes the sessions of the account in the same
    transaction (SEC-42), so the checks of the account are a second line of defense.

    Args:
        session: The stored session.
        now: The current time.
        policy: The session policy.

    Returns:
        True while the session is valid.
    """
    return (
        now < session.expires_at
        and now - session.last_seen_at < policy.idle_timeout
        and session.is_account_active
        and session.account.role is session.role_at_creation
    )


def is_touch_due(session: StoredSession, now: datetime, policy: SessionPolicy) -> bool:
    """Tell whether `last_seen_at` should be updated now.

    Args:
        session: The stored session.
        now: The current time.
        policy: The session policy.

    Returns:
        True once `touch_interval` has passed since the last touch.
    """
    return now - session.last_seen_at >= policy.touch_interval


def to_principal(account: SessionAccount) -> Principal:
    """Build the principal of an account.

    Args:
        account: The account of the session.

    Returns:
        A `CustomerPrincipal` for a customer account, an `InternalPrincipal` otherwise.
    """
    if account.customer_id is not None:
        return CustomerPrincipal(account.account_id, account.customer_id)
    return InternalPrincipal(account.account_id, InternalRole(account.role.value))
