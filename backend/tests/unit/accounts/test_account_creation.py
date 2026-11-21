"""Tests of the account creation with fakes for every port (ADR-0015, ERR-21)."""

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from app.accounts import (
    AccountChangePorts,
    AccountCreation,
    AccountCreationStores,
    AccountId,
    AdminPrincipal,
    AssignableRole,
    Authorizer,
    CreateAccount,
    DisplayName,
    InternalAccount,
    InternalRole,
    LoginName,
    LoginNameTakenError,
    LoginNumber,
    NewInternalAccount,
    Password,
    SessionRequiredError,
)
from app.audit import AuditEventType
from app.idempotency import IdempotencyGuard, IdempotencyKey, StoredResponse
from app.platform import EventName
from tests.unit.accounts.fakes import (
    FakeAccountChangeLock,
    FakeInternalAccountStore,
    build_internal_account,
)
from tests.unit.accounts.password_fakes import (
    FakeNewAccountStore,
    FakePasswordHasher,
    hash_of,
)
from tests.unit.audit.fakes import FakeAuditLog
from tests.unit.idempotency.fakes import FakeIdempotencyStore
from tests.unit.platform.fakes import (
    FakeClock,
    FakeTransactionRunner,
    FixedTraceContext,
    RecordedEvent,
    RecordingEventRecorder,
    SequentialIdGenerator,
)

pytestmark = pytest.mark.anyio

ADMIN_ID = AccountId("00000000-0000-0000-0000-0000000000a1")
ADMIN = AdminPrincipal(ADMIN_ID)
# The first ID of `SequentialIdGenerator`, which the use case draws for the new account.
NEW_ACCOUNT_ID = AccountId(str(UUID(int=1)))
LOGIN_NAMES_IN_USE = (LoginName("staff-1"), LoginName("staff-3"), LoginName("manager-8"))
FREE_NUMBER = LoginNumber(7)
TAKEN_NUMBER = LoginNumber(3)
DISPLAY_NAME = DisplayName("Lan Do")
NEW_PASSWORD = "created-test-password"
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000001"))
RETENTION_MS = 86_400_000
RESPONSE_STATUS = 201


def render(account: InternalAccount) -> StoredResponse:
    return StoredResponse(RESPONSE_STATUS, f'{{"login_name":"{account.login_name}"}}')


def creation(login_number: LoginNumber | None = FREE_NUMBER) -> AccountCreation:
    return AccountCreation(AssignableRole.STAFF, login_number, DISPLAY_NAME, Password(NEW_PASSWORD))


@dataclass(slots=True)
class CreationHarness:
    """The creation use case with its fakes, with an admin and some login names in use."""

    accounts: FakeInternalAccountStore = field(default_factory=FakeInternalAccountStore)
    new_accounts: FakeNewAccountStore = field(default_factory=FakeNewAccountStore)
    audit_log: FakeAuditLog = field(default_factory=FakeAuditLog)
    idempotency: FakeIdempotencyStore = field(default_factory=FakeIdempotencyStore)
    events: RecordingEventRecorder = field(default_factory=RecordingEventRecorder)
    clock: FakeClock = field(default_factory=FakeClock)
    transactions: FakeTransactionRunner[AccountCreationStores] = field(init=False)
    use_case: CreateAccount = field(init=False)

    def __post_init__(self) -> None:
        """Wire the use case on the fakes."""
        self.accounts.accounts = {ADMIN_ID: build_internal_account(ADMIN_ID, InternalRole.ADMIN)}
        self.new_accounts.login_names = list(LOGIN_NAMES_IN_USE)
        self.transactions = FakeTransactionRunner(
            AccountCreationStores(
                lock=FakeAccountChangeLock(self.accounts.calls),
                accounts=self.accounts,
                new_accounts=self.new_accounts,
                audit_log=self.audit_log,
                idempotency=self.idempotency,
            )
        )
        self.use_case = CreateAccount(
            self.transactions,
            AccountChangePorts(
                guard=IdempotencyGuard(self.clock, RETENTION_MS),
                authorizer=Authorizer(self.events),
                clock=self.clock,
                ids=SequentialIdGenerator(),
                traces=FixedTraceContext(),
                events=self.events,
            ),
            FakePasswordHasher(),
            render,
        )

    async def execute(self, account_creation: AccountCreation) -> StoredResponse:
        """Run the use case as the admin."""
        return await self.use_case.execute(ADMIN, account_creation, KEY)


@pytest.fixture
def harness() -> CreationHarness:
    return CreationHarness()


async def test_creation_inserts_an_active_account_with_the_hash_of_its_password(
    harness: CreationHarness,
) -> None:
    response = await harness.execute(creation())

    (saved,) = harness.new_accounts.saved
    assert saved == NewInternalAccount(
        InternalAccount(
            NEW_ACCOUNT_ID, LoginName("staff-7"), DISPLAY_NAME, InternalRole.STAFF, True
        ),
        hash_of(NEW_PASSWORD),
        harness.clock.now(),
    )
    assert response == render(saved.account)
    assert harness.transactions.commit_count == 1


@pytest.mark.parametrize(
    ("login_number", "login_name"), [(FREE_NUMBER, "staff-7"), (None, "staff-4")]
)
async def test_creation_composes_the_login_name_of_the_number_or_of_the_next_free_one(
    harness: CreationHarness, login_number: LoginNumber | None, login_name: str
) -> None:
    await harness.execute(creation(login_number))

    (saved,) = harness.new_accounts.saved
    assert saved.account.login_name == login_name


async def test_number_in_use_is_refused_and_creates_nothing(harness: CreationHarness) -> None:
    with pytest.raises(LoginNameTakenError):
        await harness.execute(creation(TAKEN_NUMBER))

    assert harness.new_accounts.saved == []
    assert harness.audit_log.entries == []
    assert harness.transactions.rollback_count == 1
    assert harness.events.names() == ()


async def test_creation_by_a_caller_no_longer_active_gets_session_required(
    harness: CreationHarness,
) -> None:
    harness.accounts.accounts[ADMIN_ID] = build_internal_account(
        ADMIN_ID, InternalRole.ADMIN, is_active=False
    )

    with pytest.raises(SessionRequiredError):
        await harness.execute(creation())

    assert harness.new_accounts.saved == []
    assert harness.transactions.rollback_count == 1


async def test_creation_writes_one_audit_entry_without_a_name_or_a_password(
    harness: CreationHarness,
) -> None:
    await harness.execute(creation())

    (entry,) = harness.audit_log.entries
    assert entry.event_type is AuditEventType.ACCOUNT_CREATED
    assert entry.actor_account_id == ADMIN_ID
    assert entry.data == {"target_account_id": NEW_ACCOUNT_ID, "role": "staff"}


async def test_creation_records_its_event_with_internal_values_only(
    harness: CreationHarness,
) -> None:
    await harness.execute(creation())

    assert harness.events.events == [
        RecordedEvent(
            EventName.ACCOUNT_CREATED,
            {"account_id": ADMIN_ID, "target_account_id": NEW_ACCOUNT_ID, "role": "staff"},
        )
    ]
