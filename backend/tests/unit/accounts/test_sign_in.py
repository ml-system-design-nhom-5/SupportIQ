"""Tests of the sign-in use case with fakes for every port (ADR-0009, ERR-21)."""

from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from app.accounts import (
    Credentials,
    InvalidCredentialsError,
    LoginName,
    Password,
    SessionPolicy,
    SessionToken,
    SignIn,
    SignInPorts,
    SignInRules,
    SignInStores,
    ThrottlePolicy,
    hash_login_name,
    hash_session_token,
)
from app.platform import MILLISECONDS_PER_SECOND, DatabaseUnavailableError, EventName
from tests.unit.accounts.fakes import (
    DUMMY_HASH,
    HASH_OF_KNOWN_PASSWORD,
    KNOWN_PASSWORD,
    TOKEN_VALUE,
    FakeAccountStore,
    FakePasswordVerifier,
    FakeSessionStore,
    FakeSignInFailureStore,
    FixedSessionTokens,
    build_session_account,
    build_sign_in_account,
)
from tests.unit.platform.fakes import FakeClock, FakeTransactionRunner, RecordingEventRecorder

pytestmark = pytest.mark.anyio

LOGIN_NAME = "staff-1"
NAME_HASH = hash_login_name(LoginName(LOGIN_NAME))
UNKNOWN_NAME = "staff-999"
WRONG_PASSWORD = "wrong-test-password"
FAILURE_LIMIT = 3
DELAY_MS = 2_000
WINDOW = timedelta(minutes=15)
SESSION_POLICY = SessionPolicy(
    idle_timeout=timedelta(minutes=30),
    absolute_lifetime=timedelta(hours=8),
    touch_interval=timedelta(minutes=1),
)


@dataclass(slots=True)
class SignInHarness:
    """The use case with its fakes."""

    accounts: FakeAccountStore = field(default_factory=FakeAccountStore)
    sessions: FakeSessionStore = field(default_factory=FakeSessionStore)
    failures: FakeSignInFailureStore = field(default_factory=FakeSignInFailureStore)
    passwords: FakePasswordVerifier = field(default_factory=FakePasswordVerifier)
    clock: FakeClock = field(default_factory=FakeClock)
    events: RecordingEventRecorder = field(default_factory=RecordingEventRecorder)
    transactions: FakeTransactionRunner[SignInStores] = field(init=False)
    use_case: SignIn = field(init=False)

    def __post_init__(self) -> None:
        """Wire the use case on the fakes."""
        self.transactions = FakeTransactionRunner(
            SignInStores(self.accounts, self.sessions, self.failures)
        )
        self.use_case = SignIn(
            self.transactions,
            SignInPorts(self.passwords, FixedSessionTokens(), self.clock, self.events),
            SignInRules(
                sessions=SESSION_POLICY,
                throttle=ThrottlePolicy(FAILURE_LIMIT, WINDOW, DELAY_MS),
                dummy_password_hash=DUMMY_HASH,
            ),
        )

    def add_account(self, *, is_active: bool = True) -> None:
        """Add the account of the login name."""
        self.accounts.accounts[LoginName(LOGIN_NAME)] = build_sign_in_account(is_active=is_active)

    async def add_failures(self, count: int) -> None:
        """Record failures of the login name at the current time."""
        self.failures.failures[NAME_HASH] = [self.clock.now()] * count


def credentials(login_name: str = LOGIN_NAME, password: str = KNOWN_PASSWORD) -> Credentials:
    return Credentials(login_name, Password(password))


@pytest.fixture
def harness() -> SignInHarness:
    return SignInHarness()


async def test_valid_credentials_create_a_session(harness: SignInHarness) -> None:
    harness.add_account()

    signed_in = await harness.use_case.execute(credentials())

    (session,) = harness.sessions.saved
    assert signed_in.token == SessionToken(TOKEN_VALUE)
    assert signed_in.account == build_session_account()
    assert session.session_id_hash == hash_session_token(SessionToken(TOKEN_VALUE))
    assert session.expires_at == harness.clock.now() + timedelta(hours=8)
    assert harness.transactions.commit_count == 1


async def test_typed_login_name_is_normalized_before_the_lookup(harness: SignInHarness) -> None:
    harness.add_account()

    signed_in = await harness.use_case.execute(credentials(login_name="  STAFF-1 "))

    assert signed_in.account == build_session_account()


async def test_success_deletes_expired_sessions_and_the_failures_of_the_name(
    harness: SignInHarness,
) -> None:
    harness.add_account()
    await harness.add_failures(FAILURE_LIMIT - 1)

    await harness.use_case.execute(credentials())

    now = harness.clock.now()
    assert harness.sessions.expired_deletions == [(now, now - timedelta(minutes=30))]
    assert harness.failures.failures == {}


async def test_success_records_session_created_without_the_login_name(
    harness: SignInHarness,
) -> None:
    harness.add_account()

    await harness.use_case.execute(credentials())

    (created,) = harness.events.of(EventName.SESSION_CREATED)
    assert created.attributes == {
        "account_id": build_session_account().account_id,
        "role": "staff",
    }


async def test_unknown_name_verifies_against_the_dummy_hash(harness: SignInHarness) -> None:
    with pytest.raises(InvalidCredentialsError):
        await harness.use_case.execute(credentials(login_name=UNKNOWN_NAME))

    assert harness.passwords.verified_hashes == [DUMMY_HASH]


async def test_deactivated_account_verifies_against_its_own_hash(harness: SignInHarness) -> None:
    harness.add_account(is_active=False)

    with pytest.raises(InvalidCredentialsError):
        await harness.use_case.execute(credentials())

    assert harness.passwords.verified_hashes == [HASH_OF_KNOWN_PASSWORD]


@pytest.mark.parametrize(
    ("login_name", "password", "is_active"),
    [
        (UNKNOWN_NAME, KNOWN_PASSWORD, True),
        (LOGIN_NAME, WRONG_PASSWORD, True),
        (LOGIN_NAME, KNOWN_PASSWORD, False),
    ],
)
async def test_every_failure_records_one_failure_and_commits_it(
    harness: SignInHarness, login_name: str, password: str, is_active: bool
) -> None:
    harness.add_account(is_active=is_active)

    with pytest.raises(InvalidCredentialsError):
        await harness.use_case.execute(credentials(login_name, password))

    assert len(harness.failures.failures[hash_login_name(LoginName(login_name))]) == 1
    assert harness.failures.expired_since_of_saves == [harness.clock.now() - WINDOW]
    assert harness.sessions.saved == []
    assert harness.transactions.commit_count == 1
    assert harness.events.names() == (EventName.SIGN_IN_FAILED,)


async def test_below_the_limit_the_password_is_still_checked(harness: SignInHarness) -> None:
    harness.add_account()
    await harness.add_failures(FAILURE_LIMIT - 1)

    await harness.use_case.execute(credentials())

    assert harness.passwords.verified_hashes == [HASH_OF_KNOWN_PASSWORD]
    assert harness.clock.sleeps_ms == []


@pytest.mark.parametrize("failure_count", [FAILURE_LIMIT, FAILURE_LIMIT + 1])
async def test_at_the_limit_even_the_right_password_waits_and_is_refused(
    harness: SignInHarness, failure_count: int
) -> None:
    harness.add_account()
    await harness.add_failures(failure_count)

    with pytest.raises(InvalidCredentialsError):
        await harness.use_case.execute(credentials())

    assert harness.clock.sleeps_ms == [DELAY_MS]
    assert harness.passwords.verified_hashes == []
    assert harness.sessions.saved == []
    assert harness.events.names() == (EventName.SIGN_IN_THROTTLED,)


async def test_throttled_attempt_waits_after_its_transaction_ended(
    harness: SignInHarness,
) -> None:
    harness.add_account()
    await harness.add_failures(FAILURE_LIMIT)

    with pytest.raises(InvalidCredentialsError):
        await harness.use_case.execute(credentials())

    assert harness.transactions.rollback_count == 1
    assert harness.transactions.commit_count == 0


async def test_unknown_name_is_throttled_like_a_known_one(harness: SignInHarness) -> None:
    unknown_hash = hash_login_name(LoginName(UNKNOWN_NAME))
    harness.failures.failures[unknown_hash] = [harness.clock.now()] * FAILURE_LIMIT

    with pytest.raises(InvalidCredentialsError):
        await harness.use_case.execute(credentials(login_name=UNKNOWN_NAME))

    assert harness.clock.sleeps_ms == [DELAY_MS]


async def test_failures_older_than_the_window_no_longer_count(harness: SignInHarness) -> None:
    harness.add_account()
    await harness.add_failures(FAILURE_LIMIT)
    harness.clock.advance(int(WINDOW.total_seconds() * MILLISECONDS_PER_SECOND))

    await harness.use_case.execute(credentials())

    assert harness.clock.sleeps_ms == []


async def test_database_failure_at_begin_reaches_the_caller() -> None:
    use_case = SignIn(
        FakeTransactionRunner(
            SignInStores(FakeAccountStore(), FakeSessionStore(), FakeSignInFailureStore()),
            begin_failure=DatabaseUnavailableError(),
        ),
        SignInPorts(
            FakePasswordVerifier(), FixedSessionTokens(), FakeClock(), RecordingEventRecorder()
        ),
        SignInRules(SESSION_POLICY, ThrottlePolicy(FAILURE_LIMIT, WINDOW, DELAY_MS), DUMMY_HASH),
    )

    with pytest.raises(DatabaseUnavailableError):
        await use_case.execute(credentials())


async def test_commit_failure_creates_no_event_and_rolls_back() -> None:
    accounts = FakeAccountStore({LoginName(LOGIN_NAME): build_sign_in_account()})
    transactions = FakeTransactionRunner(
        SignInStores(accounts, FakeSessionStore(), FakeSignInFailureStore()),
        commit_failure=DatabaseUnavailableError(),
    )
    events = RecordingEventRecorder()
    use_case = SignIn(
        transactions,
        SignInPorts(FakePasswordVerifier(), FixedSessionTokens(), FakeClock(), events),
        SignInRules(SESSION_POLICY, ThrottlePolicy(FAILURE_LIMIT, WINDOW, DELAY_MS), DUMMY_HASH),
    )

    with pytest.raises(DatabaseUnavailableError):
        await use_case.execute(credentials())

    assert transactions.rollback_count == 1
    assert events.names() == ()
