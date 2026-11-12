"""The password reset of a `staff` or `manager` account (`resetAccountPassword`, ADR-0015)."""

from collections.abc import Callable
from dataclasses import dataclass

from supportiq_backend.accounts.application.admin import AccountChangePorts
from supportiq_backend.accounts.application.authorization import require_active_admin
from supportiq_backend.accounts.application.password_replacement import (
    PasswordReplacementStores,
    ReplacePassword,
)
from supportiq_backend.accounts.domain.admin import AccountNotFoundError, InternalAccount
from supportiq_backend.accounts.domain.identity import AdminPrincipal, Principal
from supportiq_backend.accounts.domain.password_ports import PasswordHasher
from supportiq_backend.accounts.domain.passwords import (
    AdminPasswordReplacement,
    PasswordReset,
    validate_password_reset,
)
from supportiq_backend.accounts.domain.ports import (
    AccountChangeLock,
    InternalAccountStore,
)
from supportiq_backend.idempotency import (
    IdempotencyKey,
    IdempotencyStore,
    IdempotentRequest,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import EventName, OperationId, TransactionRunner


@dataclass(frozen=True, slots=True)
class PasswordResetStores:
    """The stores of one password reset, all in one transaction.

    Attributes:
        lock: The advisory lock of account changes, which every admin change takes.
        accounts: The internal accounts, for the reload of the caller and the target.
        idempotency: The idempotency records.
        replacement: The stores that the replacement writes.
    """

    lock: AccountChangeLock
    accounts: InternalAccountStore
    idempotency: IdempotencyStore
    replacement: PasswordReplacementStores


class ResetAccountPassword:
    """Replace the password of a `staff` or `manager` account (`resetAccountPassword`).

    The design's diagram, step by step: the hash before the transaction, then the advisory lock,
    the reload of the caller, the idempotency claim, the target and its rules, and the
    replacement and the stored response in one transaction. A deactivated account can be reset
    and stays deactivated.
    """

    def __init__(
        self,
        transactions: TransactionRunner[PasswordResetStores],
        ports: AccountChangePorts,
        hasher: PasswordHasher,
        render_response: Callable[[InternalAccount], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of a reset.
            ports: The ports that every account change uses.
            hasher: Hashes the password before the transaction opens.
            render_response: Writes the response of a reset, the one that every repeat of the
                request returns. The interface layer provides it.
        """
        self._transactions = transactions
        self._ports = ports
        self._hasher = hasher
        self._replace_password = ReplacePassword(ports.clock, ports.ids, ports.traces)
        self._render_response = render_response

    def require_admin(self, principal: Principal) -> AdminPrincipal:
        """Check the role of the caller before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as an admin.

        Raises:
            ForbiddenRoleError: The caller is not an admin.
        """
        return self._ports.authorizer.require_admin(principal, OperationId.RESET_ACCOUNT_PASSWORD)

    async def execute(
        self, admin: AdminPrincipal, reset: PasswordReset, key: IdempotencyKey
    ) -> StoredResponse:
        """Reset the password, or return the response of the first request with this key.

        Args:
            admin: The caller.
            reset: The account, the password, and the sign-out choice.
            key: The `Idempotency-Key`.

        Returns:
            The response of the reset.

        Raises:
            SessionRequiredError: The caller is no longer an active admin.
            AccountNotFoundError: The target is unknown or a customer account.
            AccountChangeRefusedError: The target is the caller or an admin account.
            IdempotencyKeyReusedError: The key was used with other fields than the password.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        password_hash = await self._hasher.hash_password(reset.password)
        request = _idempotent_request(admin, reset, key)
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            await stores.lock.acquire()
            await require_active_admin(stores.accounts, admin)
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            target = await _load_target(stores.accounts, admin, reset)
            replacement = AdminPasswordReplacement(
                admin_id=admin.account_id,
                account_id=target.account_id,
                login_name=target.login_name,
                password_hash=password_hash,
                is_signed_out_everywhere=reset.is_signed_out_everywhere,
            )
            await self._replace_password.apply(stores.replacement, replacement)
            response = self._render_response(target)
            await stores.idempotency.save_response(request, response)
            await transaction.commit()
        self._record_event(replacement)
        return response

    def _record_event(self, replacement: AdminPasswordReplacement) -> None:
        self._ports.events.record(
            EventName.ACCOUNT_PASSWORD_RESET,
            account_id=replacement.admin_id,
            target_account_id=replacement.account_id,
            is_signed_out_everywhere=replacement.is_signed_out_everywhere,
        )


def _idempotent_request(
    admin: AdminPrincipal, reset: PasswordReset, key: IdempotencyKey
) -> IdempotentRequest:
    # The path parameter belongs to the request, and the password does not (ERR-15).
    return build_idempotent_request(
        RequesterId(admin.account_id),
        OperationId.RESET_ACCOUNT_PASSWORD,
        key,
        {"account_id": reset.target_id, "is_signed_out_everywhere": reset.is_signed_out_everywhere},
    )


async def _load_target(
    accounts: InternalAccountStore, admin: AdminPrincipal, reset: PasswordReset
) -> InternalAccount:
    target = await accounts.load_internal(reset.target_id)
    if target is None:
        raise AccountNotFoundError
    validate_password_reset(admin, target)
    return target
