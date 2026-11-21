"""Tests of the login names of new accounts (ADR-0015, account management design)."""

import pytest

from app.accounts import (
    AssignableRole,
    LoginName,
    compose_login_name,
    compute_next_login_number,
)


def login_names(*names: str) -> tuple[LoginName, ...]:
    return tuple(LoginName(name) for name in names)


@pytest.mark.parametrize(
    ("role", "names_in_use", "expected"),
    [
        pytest.param(AssignableRole.STAFF, login_names(), "staff-1", id="none"),
        pytest.param(
            AssignableRole.STAFF,
            login_names("staff-1", "staff-2", "staff-3", "staff-10"),
            "staff-11",
            id="a-gap",
        ),
        pytest.param(
            AssignableRole.STAFF,
            login_names("manager-7", "customer-9"),
            "staff-1",
            id="another-prefix",
        ),
        # staff-3 became a manager and kept its login name, which counts for `staff-` only.
        pytest.param(
            AssignableRole.STAFF,
            login_names("manager-1", "staff-3"),
            "staff-4",
            id="an-account-whose-role-changed",
        ),
        pytest.param(
            AssignableRole.STAFF,
            login_names("staff-race", "staff-007", "staff-"),
            "staff-1",
            id="names-without-a-number",
        ),
        pytest.param(
            AssignableRole.MANAGER,
            login_names("manager-9999"),
            "manager-10000",
            id="past-the-range-of-a-chosen-number",
        ),
    ],
)
def test_next_free_login_name_follows_the_largest_number_of_its_prefix(
    role: AssignableRole, names_in_use: tuple[LoginName, ...], expected: str
) -> None:
    number = compute_next_login_number(role, names_in_use)

    login_name = compose_login_name(role, number)

    assert login_name == expected
