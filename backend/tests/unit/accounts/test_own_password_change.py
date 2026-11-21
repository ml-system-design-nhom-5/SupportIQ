"""Tests of the own password change with fakes for every port (ADR-0015, ERR-21)."""

from dataclasses import dataclass, field, replace
from datetime import timedelta
from uuid import UUID

import pytest

from app.accounts import (
    AccountChangeRefusedError,
    AccountChangeRule,
    AccountId,
    AuthenticatedSession,
    ChangeOwnPassword,
    InternalPrincipal,
    InternalRole,
    OwnAccount,
    OwnPasswordChange,
    OwnPasswordChangePorts,
    OwnPasswordChangeStores,
    Password,
    PasswordReplacementStores,
    SessionAccount,
    SessionIdHash,
    SessionRequiredError,
    ThrottlePolicy,
    hash_login_name,
)
from app.audit import AuditEventType
from app.idempotency import IdempotencyGuard, IdempotencyKey, StoredResponse
from app.platform import EventName
from tests.unit.accounts.fakes import (
    HASH_OF_KNOWN_PASSWORD,
    KNOWN_PASSWORD,
    LOGIN_NAME,
    FakePasswordVerifier,
    FakeSessionRevoker,
    FakeSignInFailureStore,
    build_session_account,
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

ACCOUNT = build_session_account()
CURRENT_SESSION = SessionIdHash(b"current-session")
SESSION = AuthenticatedSession(
    CURRENT_SESSION, InternalPrincipal(ACCOUNT.account_id, InternalRole.STAFF), ACCOUNT
)
NAME_HASH = hash_login_name(LOGIN_NAME)
OWN_ACCOUNT = OwnAccount(ACCOUNT, LOGIN_NAME, HASH_OF_KNOWN_PASSWORD, is_active=True)
NEW_PASSWORD = "new-test-password"
WRONG_PASSWORD = "wrong-test-password"
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000001"))
RETENTION_MS = 86_400_000
FAILURE_LIMIT = 3
DELAY_MS = 2_000
THROTTLE = ThrottlePolicy(FAILURE_LIMIT, timedelta(minutes=15), DELAY_MS)
RESPONSE_STATUS = 201


def render(account: SessionAccount) -> StoredResponse:
    return StoredResponse(RESPONSE_STATUS, f'{{"account_id":"{account.account_id}"}}')


def own_change(
    current_password: str = KNOWN_PASSWORD,
    *,
    new_password: str = NEW_PASSWORD,
    is_signed_out_elsewhere: bool = True,
) -> OwnPasswordChange:
    return OwnPasswordChange(
        Password(current_password), Password(new_password), is_signed_out_elsewhere
    )


@dataclass(slots=True)
class OwnChangeHarness:
    """The own password change with its fakes, for a staff account with the known password."""

    passwords: FakePasswordStore = field(default_factory=FakePasswordStore)
    revoker: FakeSessionRevoker = field(default_factory=FakeSessionRevoker)
    failures: FakeSignInFailureStore = field(default_factory=FakeSignInFailureStore)
    audit_log: FakeAuditLog = field(default_factory=FakeAuditLog)
    idempotency: FakeIdempotencyStore = field(default_factory=FakeIdempotencyStore)
    verifier: FakePasswordVerifier = field(default_factory=FakePasswordVerifier)
    events: RecordingEventRecorder = field(default_factory=RecordingEventRecorder)
    clock: FakeClock = field(default_factory=FakeClock)
    transactions: FakeTransactionRunner[OwnPasswordChangeStores] = field(init=False)
    use_case: ChangeOwnPassword = field(init=False)

    def __post_init__(self) -> None:
        """Wire the use case on the fakes."""
        self.passwords.own_accounts[ACCOUNT.account_id] = OWN_ACCOUNT
        self.transactions = FakeTransactionRunner(
            OwnPasswordChangeStores(
                idempotency=self.idempotency,
                replacement=PasswordReplacementStores(
                    passwords=self.passwords,
                    sessions=self.revoker,
                    failures=self.failures,
                    audit_log=self.audit_log,
                ),
            )
        )
        self.use_case = ChangeOwnPassword(
            self.transactions,
            OwnPasswordChangePorts(
                hasher=FakePasswordHasher(),
                verifier=self.verifier,
                guard=IdempotencyGuard(self.clock, RETENTION_MS),
                clock=self.clock,
                ids=SequentialIdGenerator(),
                traces=FixedTraceContext(),
                events=self.events,
            ),
            THROTTLE,
            render,
        )

    async def execute(self, change: OwnPasswordChange) -> StoredResponse:
        """Run the use case in the session of the account."""
        return await self.use_case.execute(SESSION, change, KEY)

    def add_failures(self, count: int) -> None:
        """Record failures of the login name at the current time."""
        self.failures.failures[NAME_HASH] = [self.clock.now()] * count


@pytest.fixture
def harness() -> OwnChangeHarness:
    return OwnChangeHarness()


async def test_change_stores_the_hash_of_the_new_password_and_returns_the_account(
    harness: OwnChangeHarness,
) -> None:
    response = await harness.execute(own_change())

    assert harness.passwords.saved_hashes == {ACCOUNT.account_id: hash_of(NEW_PASSWORD)}
    assert response == render(ACCOUNT)
    assert harness.transactions.commit_count == 1


@pytest.mark.parametrize(
    ("is_signed_out_elsewhere", "revoked_except"),
    [(True, [(ACCOUNT.account_id, CURRENT_SESSION)]), (False, [])],
)
async def test_change_ends_the_other_sessions_only_when_chosen(
    harness: OwnChangeHarness,
    is_signed_out_elsewhere: bool,
    revoked_except: list[tuple[AccountId, SessionIdHash]],
) -> None:
    await harness.execute(own_change(is_signed_out_elsewhere=is_signed_out_elsewhere))

    assert harness.revoker.revoked_except == revoked_except
    assert harness.revoker.revoked == []


async def test_change_forgets_the_sign_in_failures_of_the_login_name(
    harness: OwnChangeHarness,
) -> None:
    harness.add_failures(FAILURE_LIMIT - 1)

    await harness.execute(own_change())

    assert harness.failures.failures == {}


async def test_change_writes_one_audit_entry_without_any_password(
    harness: OwnChangeHarness,
) -> None:
    await harness.execute(own_change(is_signed_out_elsewhere=False))

    (entry,) = harness.audit_log.entries
    assert entry.event_type is AuditEventType.ACCOUNT_PASSWORD_CHANGED
    assert entry.actor_account_id == ACCOUNT.account_id
    assert entry.data == {"target_account_id": ACCOUNT.account_id, "is_signed_out_elsewhere": False}


async def test_change_records_its_event_with_internal_values_only(
    harness: OwnChangeHarness,
) -> None:
    await harness.execute(own_change())

    assert harness.events.events == [
        RecordedEvent(
            EventName.ACCOUNT_PASSWORD_CHANGED,
            {"account_id": ACCOUNT.account_id, "is_signed_out_elsewhere": True},
        )
    ]


async def test_repeat_returns_the_first_response_although_the_current_password_changed(
    harness: OwnChangeHarness,
) -> None:
    first = await harness.execute(own_change())

    repeated = await harness.execute(own_change(NEW_PASSWORD, new_password=WRONG_PASSWORD))

    assert repeated == first
    assert harness.passwords.saved_hashes == {ACCOUNT.account_id: hash_of(NEW_PASSWORD)}
    assert len(harness.audit_log.entries) == 1


async def test_at_the_limit_even_the_right_password_waits_and_is_refused_without_a_check(
    harness: OwnChangeHarness,
) -> None:
    harness.add_failures(FAILURE_LIMIT)

    with pytest.raises(AccountChangeRefusedError) as caught:
        await harness.execute(own_change())

    assert caught.value.rule is AccountChangeRule.CURRENT_PASSWORD_INCORRECT
    assert harness.verifier.verified_hashes == []
    assert harness.clock.sleeps_ms == [DELAY_MS]
    assert len(harness.failures.failures[NAME_HASH]) == FAILURE_LIMIT
    assert harness.passwords.saved_hashes == {}
    assert harness.transactions.rollback_count == 1
    assert harness.events.names() == (EventName.PASSWORD_CHANGE_THROTTLED,)


async def test_wrong_current_password_is_a_sign_in_failure_saved_after_the_rollback(
    harness: OwnChangeHarness,
) -> None:
    with pytest.raises(AccountChangeRefusedError) as caught:
        await harness.execute(own_change(WRONG_PASSWORD))

    assert caught.value.rule is AccountChangeRule.CURRENT_PASSWORD_INCORRECT
    assert harness.failures.failures[NAME_HASH] == [harness.clock.now()]
    assert harness.transactions.rollback_count == 1
    assert harness.transactions.commit_count == 1
    assert harness.passwords.saved_hashes == {}
    assert harness.audit_log.entries == []
    assert harness.events.names() == (EventName.PASSWORD_CHANGE_FAILED,)


@pytest.mark.parametrize(
    "own_accounts",
    [{}, {ACCOUNT.account_id: replace(OWN_ACCOUNT, is_active=False)}],
    ids=["account-gone", "account-deactivated"],
)
async def test_change_needs_a_session_when_the_locked_account_is_gone_or_inactive(
    harness: OwnChangeHarness, own_accounts: dict[AccountId, OwnAccount]
) -> None:
    harness.passwords.own_accounts = own_accounts

    with pytest.raises(SessionRequiredError):
        await harness.execute(own_change())

    assert harness.passwords.saved_hashes == {}
    assert harness.revoker.revoked_except == []
    assert harness.failures.failures == {}
    assert harness.audit_log.entries == []
    assert harness.idempotency.records == {}
    assert harness.events.events == []
    assert harness.transactions.rollback_count == 1
    assert harness.transactions.commit_count == 0
