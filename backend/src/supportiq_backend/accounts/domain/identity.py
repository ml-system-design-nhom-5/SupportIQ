"""Who is calling: account identifiers, roles, secrets, and principals (ADR-0009, ADR-0012)."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import NewType

# Identifiers and names. Account and customer IDs are Internal; a login name names a role and
# a number, so it is Internal too; a display name is Confidential.
AccountId = NewType("AccountId", str)
CustomerId = NewType("CustomerId", str)
LoginName = NewType("LoginName", str)
DisplayName = NewType("DisplayName", str)
# Hashes. A password hash is Confidential and is never exported (ADR-0009, statement 5).
PasswordHash = NewType("PasswordHash", str)


class Role(StrEnum):
    """The role of an account (ADR-0012). There are exactly four."""

    CUSTOMER = "customer"
    STAFF = "staff"
    MANAGER = "manager"
    ADMIN = "admin"


class InternalRole(StrEnum):
    """The role of an internal account, the only accounts that an admin sees (SEC-41)."""

    STAFF = "staff"
    MANAGER = "manager"
    ADMIN = "admin"


class AssignableRole(StrEnum):
    """A role that an admin can give an account (ADR-0012, admin limit 3)."""

    STAFF = "staff"
    MANAGER = "manager"


@dataclass(frozen=True, slots=True)
class Password:
    """A password as typed. Secret: it never appears in a log, a `repr`, or an error.

    Attributes:
        value: The password.
    """

    value: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SessionToken:
    """A raw session identifier, which exists only in the cookie (ADR-0009, statement 4).

    Attributes:
        value: The identifier. Secret.
    """

    value: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class CustomerPrincipal:
    """A signed-in customer. Every commerce and ticket query filters by its `customer_id`.

    Attributes:
        account_id: The account.
        customer_id: The simulated customer of the account.
    """

    account_id: AccountId
    customer_id: CustomerId


@dataclass(frozen=True, slots=True)
class InternalPrincipal:
    """A signed-in member of staff, manager, or admin.

    Attributes:
        account_id: The account.
        role: Its role.
    """

    account_id: AccountId
    role: InternalRole


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    """An account whose role check for an admin operation passed.

    Only `Authorizer.require_admin` creates one, so an admin use case that takes it can only
    run after the check.

    Attributes:
        account_id: The account.
    """

    account_id: AccountId


type Principal = CustomerPrincipal | InternalPrincipal
