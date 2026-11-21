"""Password changes and resets: what is asked, and what replacing a password does (ADR-0015).

A password exists only in the request that carries it. What a use case keeps afterwards is
the Argon2id hash, computed before its transaction opens (account management design, Locks).
"""

from dataclasses import dataclass, field

from app.accounts.domain.admin import (
    AccountChangeRefusedError,
    AccountChangeRule,
    InternalAccount,
)
from app.accounts.domain.identity import (
    AccountId,
    AdminPrincipal,
    InternalRole,
    LoginName,
    Password,
    PasswordHash,
)
from app.accounts.domain.sessions import SessionAccount, SessionIdHash


@dataclass(frozen=True, slots=True)
class OwnPasswordChange:
    """What the owner of an account sends to change its password (`changeOwnPassword`).

    Attributes:
        current_password: The password before the change.
        new_password: The password that replaces it.
        is_signed_out_elsewhere: Whether every other session of the account ends.
    """

    current_password: Password
    new_password: Password
    is_signed_out_elsewhere: bool


@dataclass(frozen=True, slots=True)
class PasswordReset:
    """What an admin sends to reset a password (`resetAccountPassword`).

    Attributes:
        target_id: The account, as the request sent it.
        password: The password that replaces the account's password.
        is_signed_out_everywhere: Whether every session of the account ends.
    """

    target_id: AccountId
    password: Password
    is_signed_out_everywhere: bool


@dataclass(frozen=True, slots=True)
class OwnAccount:
    """The caller's own account, as a password change loads it under its row lock.

    Attributes:
        account: The account, as `SessionView` shows it.
        login_name: Its login name, the key of its sign-in failures. Internal.
        password_hash: The Argon2id hash of its current password. Confidential.
        is_active: False once a deactivation committed, which deleted every session of it.
    """

    account: SessionAccount
    login_name: LoginName
    password_hash: PasswordHash = field(repr=False)
    is_active: bool


@dataclass(frozen=True, slots=True)
class OwnPasswordReplacement:
    """A password that the owner of an account replaces; the current session always stays.

    Attributes:
        account_id: The account, which is also the actor.
        login_name: Its login name.
        password_hash: The hash of the new password. Confidential.
        current_session: The session of the request.
        is_signed_out_elsewhere: Whether every other session of the account ends.
    """

    account_id: AccountId
    login_name: LoginName
    password_hash: PasswordHash = field(repr=False)
    current_session: SessionIdHash = field(repr=False)
    is_signed_out_elsewhere: bool


@dataclass(frozen=True, slots=True)
class AdminPasswordReplacement:
    """A password that an admin replaces with a reset.

    Attributes:
        admin_id: The admin, who is the actor.
        account_id: The `staff` or `manager` account.
        login_name: Its login name.
        password_hash: The hash of the new password. Confidential.
        is_signed_out_everywhere: Whether every session of the account ends.
    """

    admin_id: AccountId
    account_id: AccountId
    login_name: LoginName
    password_hash: PasswordHash = field(repr=False)
    is_signed_out_everywhere: bool


type PasswordReplacement = OwnPasswordReplacement | AdminPasswordReplacement


def validate_password_reset(caller: AdminPrincipal, target: InternalAccount) -> None:
    """Check a password reset against the limits of ADR-0015, in the order of the contract.

    An admin changes their own password with `changeOwnPassword`, never with a reset.

    Args:
        caller: The admin.
        target: The account as it is now, active or deactivated.

    Raises:
        AccountChangeRefusedError: The target is the caller's own account or an admin account.
    """
    if target.account_id == caller.account_id:
        raise AccountChangeRefusedError(AccountChangeRule.OWN_ACCOUNT)
    if target.role is InternalRole.ADMIN:
        raise AccountChangeRefusedError(AccountChangeRule.ADMIN_PASSWORD_UNRESETTABLE)
