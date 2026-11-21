"""Tests of the admin use cases with fakes for every port (ADR-0012, ERR-21)."""

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from app.accounts import (
    AccountChange,
    AccountChangePorts,
    AccountChangeRefusedError,
    AccountChangeRule,
    AccountChangeStores,
    AccountId,
    AccountNotFoundError,
    AdminPrincipal,
    AssignableRole,
    Authorizer,
    ChangeAccount,
    ForbiddenRoleError,
    InternalAccount,
    InternalPrincipal,
    InternalRole,
    ListAdminAccounts,
    OperationId,
    RoleChange,
    SessionRequiredError,
    StatusChange,
)
from app.audit import AuditEventType
from app.idempotency import (
    IdempotencyGuard,
    IdempotencyKey,
    IdempotencyKeyReusedError,
    StoredResponse,
)
from app.platform import (
    BackendError,
    DatabaseUnavailableError,
    EventName,
    InvalidCursorError,
)
from tests.unit.accounts.fakes import (
    FakeAccountChangeLock,
    FakeInternalAccountStore,
    FakeSessionRevoker,
    build_internal_account,
)
from tests.unit.audit.fakes import FakeAuditLog
from tests.unit.idempotency.fakes import FakeIdempotencyStore
from tests.unit.platform.fakes import (
    FAKE_TRACE_ID,
    FakeClock,
    FakeTransactionRunner,
    FixedTraceContext,
    RecordingEventRecorder,
    SequentialIdGenerator,
)

pytestmark = pytest.mark.anyio

ADMIN_ID = AccountId("00000000-0000-0000-0000-0000000000a1")
TARGET_ID = AccountId("00000000-0000-0000-0000-0000000000b1")
MANAGER_ID = AccountId("00000000-0000-0000-0000-0000000000b2")
ADMIN = AdminPrincipal(ADMIN_ID)
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000001"))
OTHER_KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000002"))
RETENTION_MS = 86_400_000
MAKE_MANAGER = RoleChange(TARGET_ID, AssignableRole.MANAGER)
DEACTIVATE = StatusChange(TARGET_ID, is_active=False)
RESPONSE_STATUS = 201


def render(account: InternalAccount) -> StoredResponse:
    return StoredResponse(RESPONSE_STATUS, f'{{"role":"{account.role.value}"}}')


@dataclass(slots=True)
class ChangeHarness:
    """The change use case with its fakes."""

    accounts: FakeInternalAccountStore = field(default_factory=FakeInternalAccountStore)
    revoker: FakeSessionRevoker = field(default_factory=FakeSessionRevoker)
    audit_log: FakeAuditLog = field(default_factory=FakeAuditLog)
    idempotency: FakeIdempotencyStore = field(default_factory=FakeIdempotencyStore)
    events: RecordingEventRecorder = field(default_factory=RecordingEventRecorder)
    clock: FakeClock = field(default_factory=FakeClock)
    lock_failure: BackendError | None = None
    commit_failure: BackendError | None = None
    transactions: FakeTransactionRunner[AccountChangeStores] = field(init=False)
    use_case: ChangeAccount = field(init=False)

    def __post_init__(self) -> None:
        """Wire the use case on the fakes, with an admin, a staff, and a manager account."""
        self.accounts.accounts = {
            ADMIN_ID: build_internal_account(ADMIN_ID, InternalRole.ADMIN),
            TARGET_ID: build_internal_account(TARGET_ID, InternalRole.STAFF),
            MANAGER_ID: build_internal_account(MANAGER_ID, InternalRole.MANAGER),
        }
        self.transactions = FakeTransactionRunner(
            AccountChangeStores(
                lock=FakeAccountChangeLock(self.accounts.calls, self.lock_failure),
                accounts=self.accounts,
                sessions=self.revoker,
                audit_log=self.audit_log,
                idempotency=self.idempotency,
            ),
            commit_failure=self.commit_failure,
        )
        self.use_case = ChangeAccount(
            self.transactions,
            AccountChangePorts(
                guard=IdempotencyGuard(self.clock, RETENTION_MS),
                authorizer=Authorizer(self.events),
                clock=self.clock,
                ids=SequentialIdGenerator(),
                traces=FixedTraceContext(),
                events=self.events,
            ),
            render,
        )

    async def execute(self, change: AccountChange, key: IdempotencyKey = KEY) -> StoredResponse:
        """Run the use case as the admin."""
        return await self.use_case.execute(ADMIN, change, key)


@pytest.fixture
def harness() -> ChangeHarness:
    return ChangeHarness()


async def test_allowed_change_updates_the_account_and_commits(harness: ChangeHarness) -> None:
    response = await harness.execute(MAKE_MANAGER)

    assert response == StoredResponse(RESPONSE_STATUS, '{"role":"manager"}')
    assert harness.accounts.accounts[TARGET_ID].role is InternalRole.MANAGER
    assert harness.transactions.commit_count == 1


async def test_lock_comes_first_and_the_caller_is_reloaded_after_it(
    harness: ChangeHarness,
) -> None:
    await harness.execute(MAKE_MANAGER)

    assert harness.accounts.calls[:2] == ["acquire_lock", "load_internal"]


async def test_change_deletes_the_sessions_of_the_account(harness: ChangeHarness) -> None:
    await harness.execute(DEACTIVATE)

    assert harness.revoker.revoked == [TARGET_ID]


async def test_role_change_writes_one_audit_entry(harness: ChangeHarness) -> None:
    await harness.execute(MAKE_MANAGER)

    (entry,) = harness.audit_log.entries
    assert entry.event_type is AuditEventType.ACCOUNT_ROLE_CHANGED
    assert entry.actor_account_id == ADMIN_ID
    assert entry.occurred_at == harness.clock.now()
    assert entry.trace_id == FAKE_TRACE_ID
    assert entry.data == {
        "target_account_id": TARGET_ID,
        "old_role": "staff",
        "new_role": "manager",
    }


async def test_status_change_writes_one_audit_entry(harness: ChangeHarness) -> None:
    await harness.execute(DEACTIVATE)

    (entry,) = harness.audit_log.entries
    assert entry.event_type is AuditEventType.ACCOUNT_STATUS_CHANGED
    assert entry.data == {
        "target_account_id": TARGET_ID,
        "old_is_active": True,
        "new_is_active": False,
    }


async def test_role_change_records_its_event_with_internal_values_only(
    harness: ChangeHarness,
) -> None:
    await harness.execute(MAKE_MANAGER)

    (event,) = harness.events.of(EventName.ACCOUNT_ROLE_CHANGED)
    assert event.attributes == {
        "account_id": ADMIN_ID,
        "target_account_id": TARGET_ID,
        "old_role": "staff",
        "new_role": "manager",
    }


async def test_status_change_records_its_event(harness: ChangeHarness) -> None:
    await harness.execute(DEACTIVATE)

    assert harness.events.names() == (EventName.ACCOUNT_STATUS_CHANGED,)


async def test_repeat_returns_the_first_response_and_changes_nothing_more(
    harness: ChangeHarness,
) -> None:
    first = await harness.execute(MAKE_MANAGER)

    repeated = await harness.execute(MAKE_MANAGER)

    assert repeated == first
    assert len(harness.audit_log.entries) == 1
    assert harness.revoker.revoked == [TARGET_ID]
    assert harness.transactions.commit_count == 1


async def test_same_key_on_another_account_is_refused(harness: ChangeHarness) -> None:
    await harness.execute(MAKE_MANAGER)

    with pytest.raises(IdempotencyKeyReusedError):
        await harness.execute(RoleChange(MANAGER_ID, AssignableRole.STAFF))


async def test_same_key_with_another_body_is_refused(harness: ChangeHarness) -> None:
    await harness.execute(MAKE_MANAGER)

    with pytest.raises(IdempotencyKeyReusedError):
        await harness.execute(RoleChange(TARGET_ID, AssignableRole.STAFF))


async def test_caller_no_longer_active_gets_session_required(harness: ChangeHarness) -> None:
    harness.accounts.accounts[ADMIN_ID] = build_internal_account(
        ADMIN_ID, InternalRole.ADMIN, is_active=False
    )

    with pytest.raises(SessionRequiredError):
        await harness.execute(MAKE_MANAGER)

    assert harness.transactions.rollback_count == 1


async def test_unknown_target_is_not_found_and_rolls_back(harness: ChangeHarness) -> None:
    with pytest.raises(AccountNotFoundError):
        await harness.execute(RoleChange(AccountId("unknown"), AssignableRole.MANAGER))

    assert harness.transactions.rollback_count == 1
    assert harness.audit_log.entries == []


async def test_refused_change_rolls_back_and_writes_nothing(harness: ChangeHarness) -> None:
    with pytest.raises(AccountChangeRefusedError) as caught:
        await harness.execute(RoleChange(MANAGER_ID, AssignableRole.STAFF))

    assert caught.value.rule is AccountChangeRule.LAST_ACTIVE_MANAGER
    assert harness.transactions.rollback_count == 1
    assert harness.audit_log.entries == []
    assert harness.revoker.revoked == []
    assert harness.events.names() == ()


async def test_failure_of_the_audit_log_rolls_the_change_back(harness: ChangeHarness) -> None:
    harness.audit_log.failure = DatabaseUnavailableError()

    with pytest.raises(DatabaseUnavailableError):
        await harness.execute(MAKE_MANAGER)

    assert harness.transactions.commit_count == 0
    assert harness.transactions.rollback_count == 1
    assert harness.events.names() == ()


async def test_failure_of_the_lock_changes_nothing() -> None:
    harness = ChangeHarness(lock_failure=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await harness.execute(MAKE_MANAGER)

    assert harness.accounts.accounts[TARGET_ID].role is InternalRole.STAFF
    assert harness.transactions.rollback_count == 1
    assert harness.events.names() == ()


async def test_failure_of_the_commit_records_no_event() -> None:
    harness = ChangeHarness(commit_failure=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await harness.execute(MAKE_MANAGER)

    assert harness.events.names() == ()


async def test_require_admin_refuses_another_role(harness: ChangeHarness) -> None:
    principal = InternalPrincipal(MANAGER_ID, InternalRole.MANAGER)

    with pytest.raises(ForbiddenRoleError):
        harness.use_case.require_admin(principal, OperationId.CHANGE_ACCOUNT_ROLE)

    assert harness.events.names() == (EventName.PERMISSION_DENIED,)


def build_list(
    *accounts: InternalAccount,
) -> tuple[ListAdminAccounts, FakeInternalAccountStore]:
    store = FakeInternalAccountStore({account.account_id: account for account in accounts})
    use_case = ListAdminAccounts(FakeTransactionRunner(store), Authorizer(RecordingEventRecorder()))
    return use_case, store


async def test_failure_of_the_list_reaches_the_caller() -> None:
    use_case, store = build_list(build_internal_account(ADMIN_ID, InternalRole.ADMIN))
    store.page_failure = DatabaseUnavailableError()

    with pytest.raises(DatabaseUnavailableError):
        await use_case.execute(ADMIN, None, 1)


async def test_list_returns_a_next_position_when_more_accounts_follow() -> None:
    first = build_internal_account(ADMIN_ID, InternalRole.ADMIN, name="An")
    second = build_internal_account(TARGET_ID, InternalRole.STAFF, name="Binh")
    use_case, _ = build_list(first, second)

    page = await use_case.execute(ADMIN, None, 1)

    assert page.items == (first,)
    assert page.next_after == ADMIN_ID


async def test_list_has_no_next_position_on_the_last_page() -> None:
    first = build_internal_account(ADMIN_ID, InternalRole.ADMIN, name="An")
    use_case, _ = build_list(first)

    page = await use_case.execute(ADMIN, None, 1)

    assert page.next_after is None


async def test_list_continues_after_the_account_of_the_cursor() -> None:
    first = build_internal_account(ADMIN_ID, InternalRole.ADMIN, name="An")
    second = build_internal_account(TARGET_ID, InternalRole.STAFF, name="Binh")
    use_case, _ = build_list(first, second)

    page = await use_case.execute(ADMIN, ADMIN_ID, 1)

    assert page.items == (second,)


async def test_list_refuses_a_cursor_that_names_no_internal_account() -> None:
    use_case, _ = build_list(build_internal_account(ADMIN_ID, InternalRole.ADMIN))

    with pytest.raises(InvalidCursorError):
        await use_case.execute(ADMIN, AccountId("unknown"), 1)
