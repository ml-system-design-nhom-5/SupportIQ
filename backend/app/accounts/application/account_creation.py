"""The creation of `staff` and `manager` accounts by an admin (`createAdminAccount`, ADR-0015)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.accounts.application.admin import AccountChangePorts
from app.accounts.application.authorization import require_active_admin
from app.accounts.domain.admin import (
    AccountCreation,
    InternalAccount,
    NewInternalAccount,
    build_created_account,
)
from app.accounts.domain.identity import AccountId, AdminPrincipal, Principal
from app.accounts.domain.login_names import (
    compose_login_name,
    compute_next_login_number,
    login_name_prefix,
)
from app.accounts.domain.password_ports import PasswordHasher
from app.accounts.domain.ports import (
    AccountChangeLock,
    InternalAccountStore,
    NewAccountStore,
)
from app.audit import (
    ActorAccountId,
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditLog,
    AuditValue,
)
from app.idempotency import (
    CanonicalValue,
    IdempotencyKey,
    IdempotencyStore,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from app.platform import EventName, OperationId, TransactionRunner


@dataclass(frozen=True, slots=True)
class AccountCreationStores:
    """The stores of one account creation, all in one transaction.

    Attributes:
        lock: The advisory lock of account changes, which the next free number needs.
        accounts: The internal accounts, for the reload of the caller.
        new_accounts: Inserts the account and tells which login names exist.
        audit_log: The audit log.
        idempotency: The idempotency records.
    """

    lock: AccountChangeLock
    accounts: InternalAccountStore
    new_accounts: NewAccountStore
    audit_log: AuditLog
    idempotency: IdempotencyStore


class CreateAccount:
    """Create an active `staff` or `manager` account with its login name (`createAdminAccount`).

    The design's diagram, step by step: the hash before the transaction, then the advisory lock,
    the reload of the caller, the idempotency claim, the login name, and the insert, the audit
    log entry, and the stored response in one transaction. The next free number is read under
    the advisory lock, so two creations never get the same number.
    """

    def __init__(
        self,
        transactions: TransactionRunner[AccountCreationStores],
        ports: AccountChangePorts,
        hasher: PasswordHasher,
        render_response: Callable[[InternalAccount], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of a creation.
            ports: The ports that every account change uses.
            hasher: Hashes the password before the transaction opens.
            render_response: Writes the response of a creation, the one that every repeat of
                the request returns. The interface layer provides it.
        """
        self._transactions = transactions
        self._ports = ports
        self._hasher = hasher
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
        return self._ports.authorizer.require_admin(principal, OperationId.CREATE_ADMIN_ACCOUNT)

    async def execute(
        self, admin: AdminPrincipal, creation: AccountCreation, key: IdempotencyKey
    ) -> StoredResponse:
        """Create the account, or return the response of the first request with this key.

        Args:
            admin: The caller.
            creation: The role, the number if any, the display name, and the password.
            key: The `Idempotency-Key`.

        Returns:
            The response of the creation, with the composed login name.

        Raises:
            SessionRequiredError: The caller is no longer an active admin.
            LoginNameTakenError: An account already has the composed login name.
            IdempotencyKeyReusedError: The key was used with other fields than the password.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        password_hash = await self._hasher.hash_password(creation.password)
        request = build_idempotent_request(
            RequesterId(admin.account_id),
            OperationId.CREATE_ADMIN_ACCOUNT,
            key,
            _canonical_request(creation),
        )
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            await stores.lock.acquire()
            await require_active_admin(stores.accounts, admin)
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            account = await self._build_account(stores.new_accounts, creation)
            created_at = self._ports.clock.now()
            await stores.new_accounts.save_new(
                NewInternalAccount(account, password_hash, created_at)
            )
            await stores.audit_log.append(self._build_audit_entry(admin, account))
            response = self._render_response(account)
            await stores.idempotency.save_response(request, response)
            await transaction.commit()
        self._ports.events.record(
            EventName.ACCOUNT_CREATED, account_id=admin.account_id, **_audit_data_of(account)
        )
        return response

    async def _build_account(
        self, new_accounts: NewAccountStore, creation: AccountCreation
    ) -> InternalAccount:
        number = creation.login_number
        if number is None:
            login_names = await new_accounts.load_login_names_with_prefix(
                login_name_prefix(creation.role)
            )
            number = compute_next_login_number(creation.role, login_names)
        account_id = AccountId(str(self._ports.ids.generate()))
        return build_created_account(
            account_id, compose_login_name(creation.role, number), creation
        )

    def _build_audit_entry(self, admin: AdminPrincipal, account: InternalAccount) -> AuditEntry:
        return AuditEntry(
            entry_id=AuditEntryId(self._ports.ids.generate()),
            occurred_at=self._ports.clock.now(),
            event_type=AuditEventType.ACCOUNT_CREATED,
            actor_account_id=ActorAccountId(admin.account_id),
            ticket_id=None,
            trace_id=self._ports.traces.current_trace_id(),
            data=_audit_data_of(account),
        )


def _canonical_request(creation: AccountCreation) -> Mapping[str, CanonicalValue]:
    # The password is left out, so no password reaches the request hash (ERR-15).
    canonical: dict[str, CanonicalValue] = {
        "role": creation.role.value,
        "display_name": creation.display_name,
    }
    if creation.login_number is not None:
        canonical["login_number"] = creation.login_number
    return canonical


def _audit_data_of(account: InternalAccount) -> dict[str, AuditValue]:
    # No entry or event holds a login name or a display name (SEC-39, LOG-29).
    return {"target_account_id": account.account_id, "role": account.role.value}
