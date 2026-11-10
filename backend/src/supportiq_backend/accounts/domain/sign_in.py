"""The rules of sign-in: login names, the throttle, and the `Origin` check (ADR-0009)."""

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta
from typing import NewType

from supportiq_backend.accounts.domain.errors import ForbiddenOriginError
from supportiq_backend.accounts.domain.identity import LoginName, Password, PasswordHash
from supportiq_backend.accounts.domain.sessions import SessionAccount

# The SHA-256 of a normalized login name. Keyed by the typed name, not the account, so an
# unknown name is slowed down exactly like a known one (backend foundation design).
LoginNameHash = NewType("LoginNameHash", bytes)


@dataclass(frozen=True, slots=True)
class Credentials:
    """What a person typed to sign in.

    Attributes:
        login_name: The login name, as typed.
        password: The password.
    """

    login_name: str
    password: Password


@dataclass(frozen=True, slots=True)
class ThrottlePolicy:
    """The sign-in throttle, from the settings (ADR-0009, statement 8).

    Attributes:
        failure_limit: The failures of a name, within the window, that start the throttle.
        failure_window: How long a failure counts.
        delay_ms: How long every attempt at the limit waits, in milliseconds.
    """

    failure_limit: int
    failure_window: timedelta
    delay_ms: int


@dataclass(frozen=True, slots=True)
class SignInAccount:
    """An account as sign-in loads it.

    Attributes:
        account: The account of the session it would get.
        is_active: Whether it can sign in.
        password_hash: Its Argon2id hash. Confidential.
    """

    account: SessionAccount
    is_active: bool
    password_hash: PasswordHash = field(repr=False)


@dataclass(frozen=True, slots=True)
class OriginPolicy:
    """The origins that may send state-changing requests (ADR-0009, statement 7).

    Attributes:
        allowed_origins: The allowed origins, compared exactly with the `Origin` header.
    """

    allowed_origins: frozenset[str]


def normalize_login_name(typed_name: str) -> LoginName:
    """Normalize a typed login name, so that `Staff-1` and `staff-1` are one name.

    Args:
        typed_name: The login name as typed.

    Returns:
        The name with Unicode compatibility forms folded, spaces around it removed, and case
        folded. Seeded names are already in this form.
    """
    return LoginName(unicodedata.normalize("NFKC", typed_name).strip().casefold())


def hash_login_name(login_name: LoginName) -> LoginNameHash:
    """Compute the key of the sign-in failures of a name.

    Args:
        login_name: The normalized login name.

    Returns:
        Its SHA-256 hash.
    """
    return LoginNameHash(hashlib.sha256(login_name.encode()).digest())


def is_throttled(failure_count: int, policy: ThrottlePolicy) -> bool:
    """Tell whether a login name has reached the failure limit.

    Args:
        failure_count: The failures of the name within the window.
        policy: The throttle policy.

    Returns:
        True at the limit and above it.
    """
    return failure_count >= policy.failure_limit


def validate_origin(origin: str | None, policy: OriginPolicy) -> None:
    """Check the `Origin` header of a state-changing request.

    Args:
        origin: The header value, or None when absent.
        policy: The origin policy.

    Raises:
        ForbiddenOriginError: The header is absent or not an allowed origin.
    """
    if origin is None or origin not in policy.allowed_origins:
        raise ForbiddenOriginError
