"""The admin use cases: listing internal accounts and changing them (ADR-0012)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import assert_never

from supportiq_backend.accounts.application.authorization import Authorizer
from supportiq_backend.accounts.domain.admin import (
    AccountChange,
    AccountNotFoundError,
    AccountPage,
    InternalAccount,
    RoleChange,
    StatusChange,
    apply_account_change,
    validate_account_change,
)
from supportiq_backend.accounts.domain.errors import SessionRequiredError
from supportiq_backend.accounts.domain.identity import (
    AccountId,
    AdminPrincipal,
    InternalRole,
    Principal,
)
from supportiq_backend.accounts.domain.ports import (
    AccountChangeLock,
    InternalAccountStore,
    SessionRevoker,
)
from supportiq_backend.audit import (
    ActorAccountId,
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditLog,
    AuditValue,
)
from supportiq_backend.idempotency import (
    CanonicalValue,
    IdempotencyGuard,
    IdempotencyKey,
    IdempotencyStore,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import (
    Clock,
    EventAttributeValue,
    EventName,
    EventRecorder,
    IdGenerator,
    InvalidCursorError,
    OperationId,
    TraceContext,
    TransactionRunner,
)


@dataclass(frozen=True, slots=True)
class AccountChangeStores:
    """The stores of one account change, all in one transaction.

    Attributes:
        lock: The advisory lock of account changes.
        accounts: The internal accounts.
        sessions: Deletes the sessions of the changed account.
        audit_log: The audit log.
        idempotency: The idempotency records.
    """

    lock: AccountChangeLock
    accounts: InternalAccountStore
    sessions: SessionRevoker
    audit_log: AuditLog
    idempotency: IdempotencyStore


@dataclass(frozen=True, slots=True)
class AccountChangePorts:
    """The ports of an account change besides its stores.

    Attributes:
        guard: The idempotency guard.
        authorizer: The role checks.
        clock: The clock.
        ids: Generates the IDs of audit log entries.
        traces: Tells the trace of the request, for the audit log.
        events: Where events are recorded.
    """

    guard: IdempotencyGuard
    authorizer: Authorizer
    clock: Clock
    ids: IdGenerator
    traces: TraceContext
    events: EventRecorder


class ChangeAccount:
    """Change the role or the status of an internal account (`changeAccountRole`, `...Status`).

    The design's diagram, step by step: the advisory lock first, then the reload of the caller,
    the rules of ADR-0012, and the update, the deletion of the sessions, and the audit log
    entry in one transaction.
    """

    def __init__(
        self,
        transactions: TransactionRunner[AccountChangeStores],
        ports: AccountChangePorts,
        render_response: Callable[[InternalAccount], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of a change.
            ports: The ports besides the stores.
            render_response: Writes the response of a successful change, the one that every
                repeat of the request returns. The interface layer provides it.
        """
        self._transactions = transactions
        self._ports = ports
        self._render_response = render_response

    def require_admin(self, principal: Principal, operation: OperationId) -> AdminPrincipal:
        """Check the role of the caller before the request is parsed.

        Args:
            principal: The caller.
            operation: The operation.

        Returns:
            The caller as an admin.

        Raises:
            ForbiddenRoleError: The caller is not an admin.
        """
        return self._ports.authorizer.require_admin(principal, operation)

    async def execute(
        self, admin: AdminPrincipal, change: AccountChange, key: IdempotencyKey
    ) -> StoredResponse:
        """Apply one change, or return the response of its first request.

        Args:
            admin: The caller.
            change: The change.
            key: The `Idempotency-Key`.

        Returns:
            The response of the change.

        Raises:
            SessionRequiredError: The caller is no longer an active admin.
            AccountNotFoundError: The target is unknown or a customer account.
            AccountChangeRefusedError: The change breaks an admin limit.
            IdempotencyKeyReusedError: The key was used with a different request.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        request = build_idempotent_request(
            RequesterId(admin.account_id),
            _operation_of(change),
            key,
            _canonical_request(change),
        )
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            await stores.lock.acquire()
            await _require_active_admin(stores.accounts, admin)
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            before = await stores.accounts.load_internal(change.target_id)
            if before is None:
                raise AccountNotFoundError
            manager_count = await stores.accounts.count_active_managers()
            validate_account_change(change, admin, before, manager_count)
            after = apply_account_change(change, before)
            await stores.accounts.save_change(after)
            await stores.sessions.delete_sessions_of(after.account_id)
            await stores.audit_log.append(self._build_audit_entry(admin, before, after))
            response = self._render_response(after)
            await stores.idempotency.save_response(request, response)
            await transaction.commit()
        self._record_event(admin, before, after)
        return response

    def _build_audit_entry(
        self, admin: AdminPrincipal, before: InternalAccount, after: InternalAccount
    ) -> AuditEntry:
        return AuditEntry(
            entry_id=AuditEntryId(self._ports.ids.generate()),
            occurred_at=self._ports.clock.now(),
            event_type=_audit_event_of(before, after),
            actor_account_id=ActorAccountId(admin.account_id),
            ticket_id=None,
            trace_id=self._ports.traces.current_trace_id(),
            data=_audit_data_of(before, after),
        )

    def _record_event(
        self, admin: AdminPrincipal, before: InternalAccount, after: InternalAccount
    ) -> None:
        attributes: dict[str, EventAttributeValue] = {
            "account_id": admin.account_id,
            **_audit_data_of(before, after),
        }
        event = (
            EventName.ACCOUNT_ROLE_CHANGED
            if before.role is not after.role
            else EventName.ACCOUNT_STATUS_CHANGED
        )
        self._ports.events.record(event, **attributes)


class ListAdminAccounts:
    """List the internal accounts, never a customer account (`listAdminAccounts`, SEC-41)."""

    def __init__(
        self, transactions: TransactionRunner[InternalAccountStore], authorizer: Authorizer
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the read.
            authorizer: The role checks.
        """
        self._transactions = transactions
        self._authorizer = authorizer

    def require_admin(self, principal: Principal) -> AdminPrincipal:
        """Check the role of the caller before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as an admin.

        Raises:
            ForbiddenRoleError: The caller is not an admin.
        """
        return self._authorizer.require_admin(principal, OperationId.LIST_ADMIN_ACCOUNTS)

    async def execute(
        self, _admin: AdminPrincipal, after: AccountId | None, limit: int
    ) -> AccountPage:
        """Load one page of internal accounts.

        Args:
            _admin: The caller; the type proves the role check, and the list depends on it no
                further.
            after: The last account of the previous page, from the cursor.
            limit: The maximum number of accounts.

        Returns:
            The page.

        Raises:
            InvalidCursorError: The cursor names no internal account.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        async with self._transactions.begin() as transaction:
            position = None
            if after is not None:
                position = await transaction.stores.load_internal(after)
                if position is None:
                    raise InvalidCursorError
            accounts = await transaction.stores.load_page(position, limit + 1)
        items = accounts[:limit]
        has_more = len(accounts) > limit
        return AccountPage(items, items[-1].account_id if has_more else None)


async def _require_active_admin(accounts: InternalAccountStore, admin: AdminPrincipal) -> None:
    # A change that committed while this request waited for the lock may have deactivated the
    # caller, whose session it deleted, so an admin deactivated by another cannot still act.
    caller = await accounts.load_internal(admin.account_id)
    if caller is None or not caller.is_active or caller.role is not InternalRole.ADMIN:
        raise SessionRequiredError


def _operation_of(change: AccountChange) -> OperationId:
    match change:
        case RoleChange():
            return OperationId.CHANGE_ACCOUNT_ROLE
        case StatusChange():
            return OperationId.CHANGE_ACCOUNT_STATUS
        case _:
            assert_never(change)


def _canonical_request(change: AccountChange) -> Mapping[str, CanonicalValue]:
    # The path parameter belongs to the request: one key must not reach two accounts.
    match change:
        case RoleChange():
            return {"account_id": change.target_id, "role": change.role.value}
        case StatusChange():
            return {"account_id": change.target_id, "is_active": change.is_active}
        case _:
            assert_never(change)


def _audit_event_of(before: InternalAccount, after: InternalAccount) -> AuditEventType:
    if before.role is not after.role:
        return AuditEventType.ACCOUNT_ROLE_CHANGED
    return AuditEventType.ACCOUNT_STATUS_CHANGED


def _audit_data_of(before: InternalAccount, after: InternalAccount) -> dict[str, AuditValue]:
    if before.role is not after.role:
        return {
            "target_account_id": after.account_id,
            "old_role": before.role.value,
            "new_role": after.role.value,
        }
    return {
        "target_account_id": after.account_id,
        "old_is_active": before.is_active,
        "new_is_active": after.is_active,
    }
