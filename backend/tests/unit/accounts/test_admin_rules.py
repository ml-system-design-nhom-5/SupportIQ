"""Tests of the admin limits, with the invariant of ADR-0012 as a property (TEST-13)."""

from dataclasses import dataclass

import pytest
from hypothesis import given
from hypothesis import strategies as st

from supportiq_backend.accounts import (
    AccountChange,
    AccountChangeRefusedError,
    AccountChangeRule,
    AccountId,
    AdminPrincipal,
    AssignableRole,
    DisplayName,
    InternalAccount,
    InternalRole,
    RoleChange,
    StatusChange,
    apply_account_change,
    is_active_manager,
    validate_account_change,
)

ADMIN_ID = AccountId("admin-under-test")
TARGET_ID = AccountId("target-under-test")
ADMIN = AdminPrincipal(ADMIN_ID)
NAME = DisplayName("Mai Nguyen")
INITIAL_ADMIN_COUNT = 2


def build_target(
    role: InternalRole = InternalRole.STAFF,
    *,
    is_active: bool = True,
    account_id: AccountId = TARGET_ID,
) -> InternalAccount:
    return InternalAccount(account_id, NAME, role, is_active)


def rule_of_refusal(
    change: AccountChange, target: InternalAccount, active_manager_count: int
) -> AccountChangeRule:
    with pytest.raises(AccountChangeRefusedError) as caught:
        validate_account_change(change, ADMIN, target, active_manager_count)
    return caught.value.rule


@pytest.mark.parametrize(
    ("change", "target", "rule"),
    [
        (
            RoleChange(ADMIN_ID, AssignableRole.MANAGER),
            build_target(InternalRole.ADMIN, account_id=ADMIN_ID),
            AccountChangeRule.OWN_ACCOUNT,
        ),
        (
            StatusChange(ADMIN_ID, is_active=False),
            build_target(InternalRole.ADMIN, account_id=ADMIN_ID),
            AccountChangeRule.OWN_ACCOUNT,
        ),
        (
            RoleChange(TARGET_ID, AssignableRole.MANAGER),
            build_target(InternalRole.ADMIN),
            AccountChangeRule.ADMIN_ROLE_UNCHANGEABLE,
        ),
        (
            RoleChange(TARGET_ID, AssignableRole.STAFF),
            build_target(InternalRole.STAFF),
            AccountChangeRule.ROLE_UNCHANGED,
        ),
        (
            RoleChange(TARGET_ID, AssignableRole.MANAGER),
            build_target(InternalRole.MANAGER),
            AccountChangeRule.ROLE_UNCHANGED,
        ),
        (
            StatusChange(TARGET_ID, is_active=True),
            build_target(is_active=True),
            AccountChangeRule.STATUS_UNCHANGED,
        ),
        (
            StatusChange(TARGET_ID, is_active=False),
            build_target(is_active=False),
            AccountChangeRule.STATUS_UNCHANGED,
        ),
        (
            RoleChange(TARGET_ID, AssignableRole.STAFF),
            build_target(InternalRole.MANAGER),
            AccountChangeRule.LAST_ACTIVE_MANAGER,
        ),
        (
            StatusChange(TARGET_ID, is_active=False),
            build_target(InternalRole.MANAGER),
            AccountChangeRule.LAST_ACTIVE_MANAGER,
        ),
    ],
)
def test_change_that_breaks_a_limit_names_the_rule(
    change: AccountChange, target: InternalAccount, rule: AccountChangeRule
) -> None:
    assert rule_of_refusal(change, target, active_manager_count=1) is rule


@pytest.mark.parametrize(
    ("change", "target"),
    [
        (RoleChange(TARGET_ID, AssignableRole.MANAGER), build_target(InternalRole.STAFF)),
        (RoleChange(TARGET_ID, AssignableRole.STAFF), build_target(InternalRole.MANAGER)),
        (StatusChange(TARGET_ID, is_active=False), build_target(InternalRole.STAFF)),
        (StatusChange(TARGET_ID, is_active=False), build_target(InternalRole.MANAGER)),
        (StatusChange(TARGET_ID, is_active=False), build_target(InternalRole.ADMIN)),
        (StatusChange(TARGET_ID, is_active=True), build_target(is_active=False)),
        (
            RoleChange(TARGET_ID, AssignableRole.STAFF),
            build_target(InternalRole.MANAGER, is_active=False),
        ),
    ],
)
def test_change_within_the_limits_is_allowed(
    change: AccountChange, target: InternalAccount
) -> None:
    validate_account_change(change, ADMIN, target, active_manager_count=2)

    assert apply_account_change(change, target) != target


@pytest.mark.parametrize(
    ("change", "target"),
    [
        (
            RoleChange(TARGET_ID, AssignableRole.STAFF),
            build_target(InternalRole.MANAGER, is_active=False),
        ),
        (StatusChange(TARGET_ID, is_active=False), build_target(InternalRole.STAFF)),
        (
            StatusChange(TARGET_ID, is_active=True),
            build_target(InternalRole.MANAGER, is_active=False),
        ),
    ],
)
def test_change_that_removes_no_active_manager_passes_with_only_one_left(
    change: AccountChange, target: InternalAccount
) -> None:
    validate_account_change(change, ADMIN, target, active_manager_count=1)

    assert apply_account_change(change, target) != target


def test_own_account_comes_before_every_other_rule() -> None:
    target = build_target(InternalRole.ADMIN, account_id=ADMIN_ID)

    rule = rule_of_refusal(RoleChange(ADMIN_ID, AssignableRole.STAFF), target, 0)

    assert rule is AccountChangeRule.OWN_ACCOUNT


def test_admin_role_comes_before_an_unchanged_value() -> None:
    target = build_target(InternalRole.ADMIN)

    rule = rule_of_refusal(RoleChange(TARGET_ID, AssignableRole.STAFF), target, 0)

    assert rule is AccountChangeRule.ADMIN_ROLE_UNCHANGEABLE


def test_unchanged_value_comes_before_the_last_active_manager() -> None:
    target = build_target(InternalRole.MANAGER)

    rule = rule_of_refusal(RoleChange(TARGET_ID, AssignableRole.MANAGER), target, 1)

    assert rule is AccountChangeRule.ROLE_UNCHANGED


def test_refusal_carries_violated_rule_as_an_extension_member() -> None:
    error = AccountChangeRefusedError(AccountChangeRule.LAST_ACTIVE_MANAGER)

    assert error.problem_extensions() == {"violated_rule": "last_active_manager"}
    assert error.detail == "The change would leave no active manager."


@dataclass(frozen=True, slots=True)
class Step:
    """One attempted change of a generated sequence.

    Attributes:
        caller_index: Picks the caller among the active admins.
        target_index: Picks the target among all accounts.
        change_kind: The change to try: 0 to 3.
    """

    caller_index: int
    target_index: int
    change_kind: int


def build_initial_accounts() -> dict[AccountId, InternalAccount]:
    roles = (
        InternalRole.ADMIN,
        InternalRole.ADMIN,
        InternalRole.MANAGER,
        InternalRole.MANAGER,
        InternalRole.STAFF,
        InternalRole.STAFF,
    )
    accounts = (
        build_target(role, account_id=AccountId(f"account-{index}"))
        for index, role in enumerate(roles)
    )
    return {account.account_id: account for account in accounts}


def build_change(step: Step, target_id: AccountId) -> AccountChange:
    changes: tuple[AccountChange, ...] = (
        RoleChange(target_id, AssignableRole.STAFF),
        RoleChange(target_id, AssignableRole.MANAGER),
        StatusChange(target_id, is_active=False),
        StatusChange(target_id, is_active=True),
    )
    return changes[step.change_kind]


def run_steps(steps: list[Step]) -> tuple[InternalAccount, ...]:
    accounts = build_initial_accounts()
    for step in steps:
        admins = [
            account.account_id
            for account in accounts.values()
            if account.is_active and account.role is InternalRole.ADMIN
        ]
        caller = AdminPrincipal(admins[step.caller_index % len(admins)])
        target = list(accounts.values())[step.target_index % len(accounts)]
        change = build_change(step, target.account_id)
        manager_count = sum(is_active_manager(account) for account in accounts.values())
        try:
            validate_account_change(change, caller, target, manager_count)
        except AccountChangeRefusedError:
            continue
        accounts[target.account_id] = apply_account_change(change, target)
    return tuple(accounts.values())


def count_active(accounts: tuple[InternalAccount, ...], role: InternalRole) -> int:
    return sum(account.is_active and account.role is role for account in accounts)


STEPS = st.lists(
    st.builds(
        Step,
        caller_index=st.integers(min_value=0, max_value=5),
        target_index=st.integers(min_value=0, max_value=5),
        change_kind=st.integers(min_value=0, max_value=3),
    ),
    max_size=40,
)


@given(STEPS)
def test_no_sequence_of_changes_leaves_no_active_manager(steps: list[Step]) -> None:
    accounts = run_steps(steps)

    assert count_active(accounts, InternalRole.MANAGER) >= 1


@given(STEPS)
def test_no_sequence_of_changes_leaves_no_active_admin(steps: list[Step]) -> None:
    accounts = run_steps(steps)

    assert count_active(accounts, InternalRole.ADMIN) >= 1


@given(STEPS)
def test_no_sequence_of_changes_touches_the_role_of_an_admin(steps: list[Step]) -> None:
    accounts = run_steps(steps)

    assert sum(account.role is InternalRole.ADMIN for account in accounts) == INITIAL_ADMIN_COUNT
