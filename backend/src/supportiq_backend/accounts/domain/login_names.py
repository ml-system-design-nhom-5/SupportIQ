"""The login names of new accounts: `<role>-<number>` and the next free number (ADR-0015).

A login name names a role and a number, never a person, so it stays Internal. The request of a
creation carries the role and maybe the number, never a name, so every name that `backend`
composes follows the pattern. A role change never renames an account, so a name keeps counting
for its prefix whatever the role of its account (account management design, Login names).
"""

import re
from collections.abc import Iterable
from typing import ClassVar, NewType

from supportiq_backend.accounts.domain.identity import AssignableRole, LoginName
from supportiq_backend.platform import BackendError, ErrorCode

# The number of a login name: a decimal number without leading zeros. Internal.
LoginNumber = NewType("LoginNumber", int)

_SEPARATOR = "-"
# Only the numbers that the pattern composes count; `staff-007` or `staff-x` hold none.
_NUMBER_PATTERN = re.compile(r"[1-9][0-9]*")
# The largest number of a prefix that no login name has yet, so its next free number is 1.
_NO_NUMBER = 0


class LoginNameTakenError(BackendError):
    """An account already has the login name that a creation composes (contract `409`)."""

    code: ClassVar[ErrorCode] = ErrorCode.LOGIN_NAME_TAKEN

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("An account already has this login name.")


def login_name_prefix(role: AssignableRole) -> str:
    """Return the part of a login name before its number, such as `staff-`.

    Args:
        role: The role of the account.

    Returns:
        The role and the separator.
    """
    return role.value + _SEPARATOR


def compose_login_name(role: AssignableRole, number: LoginNumber) -> LoginName:
    """Compose the login name of a new account, such as `staff-4`.

    Args:
        role: The role of the new account.
        number: The number of its login name.

    Returns:
        The login name, already in the normalized form of sign-in.
    """
    return LoginName(f"{login_name_prefix(role)}{number}")


def compute_next_login_number(
    role: AssignableRole, login_names: Iterable[LoginName]
) -> LoginNumber:
    """Compute the next free number of a role: one more than the largest number in use.

    A number is never reused, because accounts are never deleted. The range of a number that an
    admin enters does not limit this one: after 9 999 comes 10 000.

    Args:
        role: The role of the new account.
        login_names: The login names of every account, whatever its role or status.

    Returns:
        One more than the largest number of a name with the prefix of the role, or 1 when no
        such name has a number.
    """
    prefix = login_name_prefix(role)
    suffixes = (name.removeprefix(prefix) for name in login_names if name.startswith(prefix))
    numbers = (int(suffix) for suffix in suffixes if _NUMBER_PATTERN.fullmatch(suffix))
    return LoginNumber(max(numbers, default=_NO_NUMBER) + 1)
