"""The own password change of every role (`changeOwnPassword`, ADR-0015)."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from supportiq_backend.accounts.application.password_replacement import (
    PasswordReplacementStores,
    ReplacePassword,
)
from supportiq_backend.accounts.application.throttle import SignInThrottle
from supportiq_backend.accounts.domain.admin import AccountChangeRefusedError, AccountChangeRule
from supportiq_backend.accounts.domain.errors import SessionRequiredError
from supportiq_backend.accounts.domain.identity import AccountId, Password
from supportiq_backend.accounts.domain.password_ports import PasswordHasher, PasswordStore
from supportiq_backend.accounts.domain.passwords import (
    OwnAccount,
    OwnPasswordChange,
    OwnPasswordReplacement,
)
from supportiq_backend.accounts.domain.ports import PasswordVerifier
from supportiq_backend.accounts.domain.sessions import AuthenticatedSession, SessionAccount
from supportiq_backend.accounts.domain.sign_in import ThrottlePolicy, hash_login_name
from supportiq_backend.idempotency import (
    IdempotencyGuard,
    IdempotencyKey,
    IdempotencyStore,
    IdempotentRequest,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import (
    Clock,
    EventName,
    EventRecorder,
    IdGenerator,
    OperationId,
    TraceContext,
    Transaction,
    TransactionRunner,
)


@dataclass(frozen=True, slots=True)
class OwnPasswordChangeStores:
    """The stores of an own password change, all in one transaction.

    Attributes:
        idempotency: The idempotency records.
        replacement: The stores of the replacement. Its password store also loads and locks
            the caller's account, and its failure store counts the failures of the name.
    """

    idempotency: IdempotencyStore
    replacement: PasswordReplacementStores


@dataclass(frozen=True, slots=True)
class OwnPasswordChangePorts:
    """The ports of an own password change besides its stores.

    Attributes:
        hasher: Hashes the new password before the transaction opens.
        verifier: Verifies the current password.
        guard: The idempotency guard.
        clock: The clock.
        ids: Generates the IDs of audit log entries.
        traces: Tells the trace of the request, for the audit log.
        events: Where events are recorded.
    """

    hasher: PasswordHasher
    verifier: PasswordVerifier
    guard: IdempotencyGuard
    clock: Clock
    ids: IdGenerator
    traces: TraceContext
    events: EventRecorder


class _Refusal(StrEnum):
    # Why the current password was not accepted; both answer `current_password_incorrect`.
    THROTTLED = "throttled"
    INCORRECT = "incorrect"


class ChangeOwnPassword:
    """Replace the password of the caller's own account, whatever its role (`changeOwnPassword`).

    The design's diagram, step by step: the hash before the transaction, then the row lock of
    the caller's account, the idempotency claim, the throttle, the check of the current
    password, and the writes. No advisory lock is taken, so no other account waits.
    """

    def __init__(
        self,
        transactions: TransactionRunner[OwnPasswordChangeStores],
        ports: OwnPasswordChangePorts,
        throttle: ThrottlePolicy,
        render_response: Callable[[SessionAccount], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transactions of a change.
            ports: The ports besides the stores.
            throttle: The sign-in throttle, which a wrong current password counts toward.
            render_response: Writes the response of a successful change, the one that every
                repeat of the request returns. The interface layer provides it.
        """
        self._transactions = transactions
        self._ports = ports
        self._throttle = SignInThrottle(ports.clock, throttle)
        self._replace_password = ReplacePassword(ports.clock, ports.ids, ports.traces)
        self._render_response = render_response

    async def execute(
        self, session: AuthenticatedSession, change: OwnPasswordChange, key: IdempotencyKey
    ) -> StoredResponse:
        """Change the password, or return the response of the first request with this key.

        The key is claimed before the current password is checked, so a repeat of a request
        that succeeded returns its response, although its current password no longer matches.

        Args:
            session: The session of the request, which always stays.
            change: The passwords and the sign-out choice.
            key: The `Idempotency-Key`.

        Returns:
            The response of the change.

        Raises:
            SessionRequiredError: The account of the session no longer exists, or a
                deactivation committed while the request waited for its row lock.
            AccountChangeRefusedError: The current password is wrong, or the login name is at
                the failure limit, with `current_password_incorrect`.
            IdempotencyKeyReusedError: The key was used with another sign-out choice.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        password_hash = await self._ports.hasher.hash_password(change.new_password)
        request = _idempotent_request(session.principal.account_id, change, key)
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            account = await _load_own_account(stores.replacement.passwords, session)
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            refusal = await self._find_refusal(stores, account, change.current_password)
            if refusal is None:
                replacement = OwnPasswordReplacement(
                    account_id=account.account.account_id,
                    login_name=account.login_name,
                    password_hash=password_hash,
                    current_session=session.session_id_hash,
                    is_signed_out_elsewhere=change.is_signed_out_elsewhere,
                )
                return await self._replace(transaction, request, replacement, account.account)
        raise await self._refused(refusal, account)

    async def _find_refusal(
        self, stores: OwnPasswordChangeStores, account: OwnAccount, current_password: Password
    ) -> _Refusal | None:
        failures = stores.replacement.failures
        name_hash = hash_login_name(account.login_name)
        failure_count = await self._throttle.load_recent_failure_count(failures, name_hash)
        if self._throttle.is_at_limit(failure_count):
            return _Refusal.THROTTLED
        if not await self._ports.verifier.verify(account.password_hash, current_password):
            return _Refusal.INCORRECT
        return None

    async def _replace(
        self,
        transaction: Transaction[OwnPasswordChangeStores],
        request: IdempotentRequest,
        replacement: OwnPasswordReplacement,
        account: SessionAccount,
    ) -> StoredResponse:
        await self._replace_password.apply(transaction.stores.replacement, replacement)
        response = self._render_response(account)
        await transaction.stores.idempotency.save_response(request, response)
        await transaction.commit()
        self._ports.events.record(
            EventName.ACCOUNT_PASSWORD_CHANGED,
            account_id=replacement.account_id,
            is_signed_out_elsewhere=replacement.is_signed_out_elsewhere,
        )
        return response

    async def _refused(self, refusal: _Refusal, account: OwnAccount) -> AccountChangeRefusedError:
        # The transaction of the change has rolled back, so its idempotency record is gone
        # and no connection or lock is held while the throttle waits.
        account_id = account.account.account_id
        match refusal:
            case _Refusal.THROTTLED:
                self._ports.events.record(
                    EventName.PASSWORD_CHANGE_THROTTLED, account_id=account_id
                )
                await self._throttle.wait()
            case _Refusal.INCORRECT:
                await self._save_failure(account)
                self._ports.events.record(EventName.PASSWORD_CHANGE_FAILED, account_id=account_id)
            case _:
                assert_never(refusal)
        return AccountChangeRefusedError(AccountChangeRule.CURRENT_PASSWORD_INCORRECT)

    async def _save_failure(self, account: OwnAccount) -> None:
        # A wrong current password counts as a sign-in failure of the login name, in a
        # transaction of its own (ADR-0009, statement 8).
        async with self._transactions.begin() as transaction:
            failures = transaction.stores.replacement.failures
            await self._throttle.save_failure(failures, hash_login_name(account.login_name))
            await transaction.commit()


async def _load_own_account(passwords: PasswordStore, session: AuthenticatedSession) -> OwnAccount:
    # A deactivation that committed while this request waited for the row lock deleted the
    # session of the request, so the caller can no longer act (as `require_active_admin`).
    account = await passwords.load_own_account(session.principal.account_id)
    if account is None or not account.is_active:
        raise SessionRequiredError
    return account


def _idempotent_request(
    account_id: AccountId, change: OwnPasswordChange, key: IdempotencyKey
) -> IdempotentRequest:
    # No password field reaches the request hash (ERR-15, account management design).
    return build_idempotent_request(
        RequesterId(account_id),
        OperationId.CHANGE_OWN_PASSWORD,
        key,
        {"is_signed_out_elsewhere": change.is_signed_out_elsewhere},
    )
