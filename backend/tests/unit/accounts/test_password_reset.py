"""Tests of the password reset with fakes for every port (ADR-0015, ERR-21)."""

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from app.accounts import (
    AccountChangePorts,
    AccountChangeRefusedError,
    AccountChangeRule,
    AccountId,
    AccountNotFoundError,
    AdminPrincipal,
    Authorizer,
    InternalAccount,
    InternalRole,
    LoginName,
    Password,
    PasswordReplacementStores,
    PasswordReset,
    PasswordResetStores,
    ResetAccountPassword,
    SessionRequiredError,
    hash_login_name,
)
from app.audit import AuditEventType
from app.idempotency import IdempotencyGuard, IdempotencyKey, StoredResponse
from app.platform import EventName
from tests.unit.accounts.fakes import (
    FakeAccountChangeLock,
    FakeInternalAccountStore,
    FakeSessionRevoker,
    FakeSignInFailureStore,
    build_internal_account,
)
from tests.unit.accounts.password_fakes import (
    FakePasswordHasher,
    FakePasswordStore,
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
OTHER_ADMIN_ID = AccountId("00000000-0000-0000-0000-0000000000a2")
TARGET_ID = AccountId("00000000-0000-0000-0000-0000000000b1")
ADMIN = AdminPrincipal(ADMIN_ID)
TARGET_LOGIN_NAME = LoginName("staff-2")
TARGET_NAME_HASH = hash_login_name(TARGET_LOGIN_NAME)
NEW_PASSWORD = "reset-test-password"
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000001"))
RETENTION_MS = 86_400_000
RESPONSE_STATUS = 201


def render(account: InternalAccount) -> StoredResponse:
    return StoredResponse(RESPONSE_STATUS, f'{{"login_name":"{account.login_name}"}}')


def reset(
    target_id: AccountId = TARGET_ID, *, is_signed_out_everywhere: bool = True
) -> PasswordReset:
    return PasswordReset(target_id, Password(NEW_PASSWORD), is_signed_out_everywhere)


@dataclass(slots=True)
class ResetHarness:
    """The reset use case with its fakes, with two admins and a staff account."""

    accounts: FakeInternalAccountStore = field(default_factory=FakeInternalAccountStore)
    passwords: FakePasswordStore = field(default_factory=FakePasswordStore)
    revoker: FakeSessionRevoker = field(default_factory=FakeSessionRevoker)
    failures: FakeSignInFailureStore = field(default_factory=FakeSignInFailureStore)
    audit_log: FakeAuditLog = field(default_factory=FakeAuditLog)
    idempotency: FakeIdempotencyStore = field(default_factory=FakeIdempotencyStore)
    events: RecordingEventRecorder = field(default_factory=RecordingEventRecorder)
    clock: FakeClock = field(default_factory=FakeClock)
    transactions: FakeTransactionRunner[PasswordResetStores] = field(init=False)
    use_case: ResetAccountPassword = field(init=False)

    def __post_init__(self) -> None:
        """Wire the use case on the fakes."""
        self.accounts.accounts = {
            ADMIN_ID: build_internal_account(ADMIN_ID, InternalRole.ADMIN),
            OTHER_ADMIN_ID: build_internal_account(OTHER_ADMIN_ID, InternalRole.ADMIN),
            TARGET_ID: build_internal_account(
                TARGET_ID, InternalRole.STAFF, login_name=TARGET_LOGIN_NAME
            ),
        }
        self.transactions = FakeTransactionRunner(
            PasswordResetStores(
                lock=FakeAccountChangeLock(self.accounts.calls),
                accounts=self.accounts,
                idempotency=self.idempotency,
                replacement=PasswordReplacementStores(
                    passwords=self.passwords,
                    sessions=self.revoker,
                    failures=self.failures,
                    audit_log=self.audit_log,
                ),
            )
        )
        self.use_case = ResetAccountPassword(
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

    async def execute(self, password_reset: PasswordReset) -> StoredResponse:
        """Run the use case as the admin."""
        return await self.use_case.execute(ADMIN, password_reset, KEY)


@pytest.fixture
def harness() -> ResetHarness:
    return ResetHarness()


@pytest.mark.parametrize(
    ("target_id", "rule"),
    [
        (ADMIN_ID, AccountChangeRule.OWN_ACCOUNT),
        (OTHER_ADMIN_ID, AccountChangeRule.ADMIN_PASSWORD_UNRESETTABLE),
    ],
)
async def test_refused_reset_names_the_first_rule_and_changes_nothing(
    harness: ResetHarness, target_id: AccountId, rule: AccountChangeRule
) -> None:
    with pytest.raises(AccountChangeRefusedError) as caught:
        await harness.execute(reset(target_id))

    assert caught.value.rule is rule
    assert harness.passwords.saved_hashes == {}
    assert harness.audit_log.entries == []
    assert harness.transactions.rollback_count == 1


async def test_reset_of_an_unknown_account_id_is_not_found(
    harness: ResetHarness,
) -> None:
    with pytest.raises(AccountNotFoundError):
        await harness.execute(reset(AccountId("not-an-internal-account")))

    assert harness.passwords.saved_hashes == {}
    assert harness.transactions.rollback_count == 1


async def test_reset_by_a_caller_no_longer_active_gets_session_required(
    harness: ResetHarness,
) -> None:
    harness.accounts.accounts[ADMIN_ID] = build_internal_account(
        ADMIN_ID, InternalRole.ADMIN, is_active=False
    )

    with pytest.raises(SessionRequiredError):
        await harness.execute(reset())

    assert harness.passwords.saved_hashes == {}
    assert harness.transactions.rollback_count == 1


async def test_reset_stores_only_the_hash_even_of_a_deactivated_account(
    harness: ResetHarness,
) -> None:
    deactivated = build_internal_account(
        TARGET_ID, InternalRole.STAFF, is_active=False, login_name=TARGET_LOGIN_NAME
    )
    harness.accounts.accounts[TARGET_ID] = deactivated

    response = await harness.execute(reset())

    assert harness.passwords.saved_hashes == {TARGET_ID: hash_of(NEW_PASSWORD)}
    assert harness.accounts.accounts[TARGET_ID] == deactivated
    assert response == render(deactivated)
    assert harness.transactions.commit_count == 1


@pytest.mark.parametrize(
    ("is_signed_out_everywhere", "revoked"), [(True, [TARGET_ID]), (False, [])]
)
async def test_reset_ends_every_session_only_when_chosen(
    harness: ResetHarness, is_signed_out_everywhere: bool, revoked: list[AccountId]
) -> None:
    await harness.execute(reset(is_signed_out_everywhere=is_signed_out_everywhere))

    assert harness.revoker.revoked == revoked
    assert harness.revoker.revoked_except == []


async def test_reset_forgets_the_sign_in_failures_of_the_login_name(
    harness: ResetHarness,
) -> None:
    harness.failures.failures[TARGET_NAME_HASH] = [harness.clock.now()]

    await harness.execute(reset())

    assert harness.failures.failures == {}


async def test_reset_writes_one_audit_entry_without_any_password(harness: ResetHarness) -> None:
    await harness.execute(reset())

    (entry,) = harness.audit_log.entries
    assert entry.event_type is AuditEventType.ACCOUNT_PASSWORD_RESET
    assert entry.actor_account_id == ADMIN_ID
    assert entry.data == {"target_account_id": TARGET_ID, "is_signed_out_everywhere": True}


async def test_reset_records_its_event_with_internal_values_only(harness: ResetHarness) -> None:
    await harness.execute(reset(is_signed_out_everywhere=False))

    assert harness.events.events == [
        RecordedEvent(
            EventName.ACCOUNT_PASSWORD_RESET,
            {
                "account_id": ADMIN_ID,
                "target_account_id": TARGET_ID,
                "is_signed_out_everywhere": False,
            },
        )
    ]
