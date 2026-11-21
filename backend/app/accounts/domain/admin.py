"""The limits on changes of internal accounts, as pure rules (ADR-0012, ADR-0015).

The values of `AccountChangeRule` are those of the contract. Every change goes through one
validation, which checks the limits in the order of the contract, so the first value of the
list is the one reported when several apply. At least one active admin always stays: the
caller is an active admin and cannot change their own account.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import assert_never

from app.accounts.domain.identity import (
    AccountId,
    AdminPrincipal,
    AssignableRole,
    DisplayName,
    InternalRole,
    LoginName,
    Password,
    PasswordHash,
)
from app.accounts.domain.login_names import LoginNumber
from app.platform import InvalidRequestError, ResourceNotFoundError

# The role that is a change's target, for the comparison with an internal role.
_INTERNAL_ROLE_OF: Mapping[AssignableRole, InternalRole] = MappingProxyType(
    {
        AssignableRole.STAFF: InternalRole.STAFF,
        AssignableRole.MANAGER: InternalRole.MANAGER,
    }
)


class AccountChangeRule(StrEnum):
    """Why a well-formed account change was refused, in the order of the contract."""

    OWN_ACCOUNT = "own_account"
    ADMIN_ROLE_UNCHANGEABLE = "admin_role_unchangeable"
    ROLE_UNCHANGED = "role_unchanged"
    STATUS_UNCHANGED = "status_unchanged"
    LAST_ACTIVE_MANAGER = "last_active_manager"
    ADMIN_PASSWORD_UNRESETTABLE = "admin_password_unresettable"  # noqa: S105  # a rule name
    CURRENT_PASSWORD_INCORRECT = "current_password_incorrect"  # noqa: S105  # a rule name


_DETAIL_OF_RULE: Mapping[AccountChangeRule, str] = MappingProxyType(
    {
        AccountChangeRule.OWN_ACCOUNT: "An admin cannot change their own account.",
        AccountChangeRule.ADMIN_ROLE_UNCHANGEABLE: (
            "The role of an admin account cannot be changed."
        ),
        AccountChangeRule.ROLE_UNCHANGED: "The account already has this role.",
        AccountChangeRule.STATUS_UNCHANGED: "The account already has this status.",
        AccountChangeRule.LAST_ACTIVE_MANAGER: "The change would leave no active manager.",
        AccountChangeRule.ADMIN_PASSWORD_UNRESETTABLE: (
            "The password of an admin account cannot be reset."
        ),
        AccountChangeRule.CURRENT_PASSWORD_INCORRECT: "The current password is not correct.",
    }
)


class AccountChangeRefusedError(InvalidRequestError):
    """A well-formed change breaks an admin limit (`422` with `violated_rule`)."""

    def __init__(self, rule: AccountChangeRule) -> None:
        """Build the error from the rule.

        Args:
            rule: The first limit that the change breaks.
        """
        super().__init__(_DETAIL_OF_RULE[rule])
        self.rule = rule

    def problem_extensions(self) -> Mapping[str, str]:
        """Return the `violated_rule` extension member of the contract.

        Returns:
            The extension member.
        """
        return {"violated_rule": self.rule.value}


class AccountNotFoundError(ResourceNotFoundError):
    """The target is unknown or a customer account, which an admin never sees (SEC-41)."""


@dataclass(frozen=True, slots=True)
class InternalAccount:
    """A `staff`, `manager`, or `admin` account as the admin area sees it.

    Attributes:
        account_id: The account.
        login_name: The name it signs in with, a role and a number. Internal.
        display_name: The name shown for it. Confidential.
        role: Its role.
        is_active: Whether it can sign in.
    """

    account_id: AccountId
    login_name: LoginName
    display_name: DisplayName = field(repr=False)
    role: InternalRole
    is_active: bool


@dataclass(frozen=True, slots=True)
class RoleChange:
    """A change of role.

    Attributes:
        target_id: The account to change.
        role: The role that the account gets.
    """

    target_id: AccountId
    role: AssignableRole


@dataclass(frozen=True, slots=True)
class StatusChange:
    """A deactivation or a reactivation.

    Attributes:
        target_id: The account to change.
        is_active: The status that the account gets.
    """

    target_id: AccountId
    is_active: bool


type AccountChange = RoleChange | StatusChange


@dataclass(frozen=True, slots=True)
class AccountCreation:
    """A `staff` or `manager` account that an admin creates (`createAdminAccount`, ADR-0015).

    Attributes:
        role: Its role, which also starts its login name.
        login_number: The number of its login name; absent for the next free number.
        display_name: The name shown for it. Confidential.
        password: Its first password, which the admin hands over outside the system.
    """

    role: AssignableRole
    login_number: LoginNumber | None
    display_name: DisplayName = field(repr=False)
    password: Password


@dataclass(frozen=True, slots=True)
class NewInternalAccount:
    """An account to insert, with the hash of its first password.

    Attributes:
        account: The account, active from the start.
        password_hash: The Argon2id hash of its password. Confidential.
        created_at: When it was created.
    """

    account: InternalAccount
    password_hash: PasswordHash = field(repr=False)
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AccountPage:
    """One page of internal accounts.

    Attributes:
        items: The accounts of the page.
        next_after: The last account of the page when more follow; absent on the last page.
    """

    items: tuple[InternalAccount, ...]
    next_after: AccountId | None


def validate_account_change(
    change: AccountChange,
    caller: AdminPrincipal,
    target: InternalAccount,
    active_manager_count: int,
) -> None:
    """Check a change against the admin limits, in the order of the contract.

    Args:
        change: The change.
        caller: The admin.
        target: The account as it is now.
        active_manager_count: The active managers now, read under the advisory lock.

    Raises:
        AccountChangeRefusedError: The change breaks a limit.
    """
    if target.account_id == caller.account_id:
        raise AccountChangeRefusedError(AccountChangeRule.OWN_ACCOUNT)
    match change:
        case RoleChange():
            _validate_role_change(change, target)
        case StatusChange():
            _validate_status_change(change, target)
        case _:
            assert_never(change)
    removes_manager = removes_active_manager(target, apply_account_change(change, target))
    if removes_manager and active_manager_count <= 1:
        raise AccountChangeRefusedError(AccountChangeRule.LAST_ACTIVE_MANAGER)


def build_created_account(
    account_id: AccountId, login_name: LoginName, creation: AccountCreation
) -> InternalAccount:
    """Build the account that a creation adds: active, with the role that it asks for.

    Args:
        account_id: The identifier of the new account.
        login_name: Its composed login name.
        creation: What the admin asked for.

    Returns:
        The new account.
    """
    return InternalAccount(
        account_id=account_id,
        login_name=login_name,
        display_name=creation.display_name,
        role=_INTERNAL_ROLE_OF[creation.role],
        is_active=True,
    )


def apply_account_change(change: AccountChange, target: InternalAccount) -> InternalAccount:
    """Compute the account after a change.

    Args:
        change: The change.
        target: The account before the change.

    Returns:
        The account after the change.
    """
    match change:
        case RoleChange():
            return replace(target, role=_INTERNAL_ROLE_OF[change.role])
        case StatusChange():
            return replace(target, is_active=change.is_active)
        case _:
            assert_never(change)


def removes_active_manager(before: InternalAccount, after: InternalAccount) -> bool:
    """Tell whether a change takes an active manager away.

    Args:
        before: The account before the change.
        after: The account after the change.

    Returns:
        True when the account was an active manager and no longer is.
    """
    return is_active_manager(before) and not is_active_manager(after)


def is_active_manager(account: InternalAccount) -> bool:
    """Tell whether an account counts as an active manager.

    Args:
        account: The account.

    Returns:
        True for an active account with the role `manager`.
    """
    return account.is_active and account.role is InternalRole.MANAGER


def _validate_role_change(change: RoleChange, target: InternalAccount) -> None:
    if target.role is InternalRole.ADMIN:
        raise AccountChangeRefusedError(AccountChangeRule.ADMIN_ROLE_UNCHANGEABLE)
    if target.role is _INTERNAL_ROLE_OF[change.role]:
        raise AccountChangeRefusedError(AccountChangeRule.ROLE_UNCHANGED)


def _validate_status_change(change: StatusChange, target: InternalAccount) -> None:
    if target.is_active is change.is_active:
        raise AccountChangeRefusedError(AccountChangeRule.STATUS_UNCHANGED)
