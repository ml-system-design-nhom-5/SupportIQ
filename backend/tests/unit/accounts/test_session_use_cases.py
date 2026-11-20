"""Tests of authentication, sign-out, and the role checks with fakes (ADR-0009, SEC-16)."""

from datetime import timedelta

import pytest

from app.accounts import (
    AdminPrincipal,
    AuthenticatedSession,
    AuthenticateSession,
    Authorizer,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
    OperationId,
    Principal,
    SessionPolicy,
    SessionRequiredError,
    SessionToken,
    SignOut,
    hash_session_token,
)
from app.platform import DatabaseUnavailableError, EventName
from tests.unit.accounts.fakes import (
    CUSTOMER_ACCOUNT_ID,
    CUSTOMER_ID,
    STAFF_ACCOUNT_ID,
    FakeSessionStore,
    build_session_account,
    build_stored_session,
)
from tests.unit.platform.fakes import FakeClock, FakeTransactionRunner, RecordingEventRecorder

pytestmark = pytest.mark.anyio

TOKEN = SessionToken("session-of-this-test")
SESSION_ID_HASH = hash_session_token(TOKEN)
POLICY = SessionPolicy(
    idle_timeout=timedelta(minutes=30),
    absolute_lifetime=timedelta(hours=8),
    touch_interval=timedelta(minutes=1),
)
CUSTOMER = CustomerPrincipal(CUSTOMER_ACCOUNT_ID, CUSTOMER_ID)
ADMIN = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.ADMIN)
STAFF = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.STAFF)
MANAGER = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.MANAGER)


def build_authenticate(
    store: FakeSessionStore, clock: FakeClock
) -> tuple[AuthenticateSession, FakeTransactionRunner[FakeSessionStore]]:
    transactions = FakeTransactionRunner(store)
    return AuthenticateSession(transactions, clock, POLICY), transactions


def store_with_session() -> FakeSessionStore:
    store = FakeSessionStore()
    store.sessions[SESSION_ID_HASH] = build_stored_session(session_id_hash=SESSION_ID_HASH)
    return store


async def test_request_without_a_cookie_has_no_session() -> None:
    use_case, _ = build_authenticate(FakeSessionStore(), FakeClock())

    with pytest.raises(SessionRequiredError):
        await use_case.authenticate(None)


async def test_unknown_cookie_has_no_session_and_changes_nothing() -> None:
    store = FakeSessionStore()
    use_case, transactions = build_authenticate(store, FakeClock())

    with pytest.raises(SessionRequiredError):
        await use_case.authenticate(TOKEN)

    assert transactions.commit_count == 0
    assert store.deleted == []


async def test_valid_session_returns_its_principal_and_account() -> None:
    use_case, _ = build_authenticate(store_with_session(), FakeClock())

    session = await use_case.authenticate(TOKEN)

    assert session == AuthenticatedSession(SESSION_ID_HASH, STAFF, build_session_account())


async def test_read_within_the_touch_interval_writes_nothing() -> None:
    store = store_with_session()
    clock = FakeClock()
    use_case, transactions = build_authenticate(store, clock)
    clock.advance(59_999)

    await use_case.authenticate(TOKEN)

    assert store.touches == []
    assert transactions.commit_count == 0


async def test_read_after_the_touch_interval_updates_last_seen_at() -> None:
    store = store_with_session()
    clock = FakeClock()
    use_case, transactions = build_authenticate(store, clock)
    clock.advance(60_000)

    await use_case.authenticate(TOKEN)

    assert store.touches == [clock.now()]
    assert transactions.commit_count == 1


async def test_idle_session_is_deleted_and_refused() -> None:
    store = store_with_session()
    clock = FakeClock()
    use_case, transactions = build_authenticate(store, clock)
    clock.advance(1_800_000)

    with pytest.raises(SessionRequiredError):
        await use_case.authenticate(TOKEN)

    assert store.deleted == [SESSION_ID_HASH]
    assert transactions.commit_count == 1


async def test_session_past_its_lifetime_is_deleted_and_refused() -> None:
    store = FakeSessionStore()
    clock = FakeClock()
    store.sessions[SESSION_ID_HASH] = build_stored_session(
        session_id_hash=SESSION_ID_HASH,
        last_seen_at=clock.now(),
        expires_at=clock.now(),
    )
    use_case, _ = build_authenticate(store, clock)

    with pytest.raises(SessionRequiredError):
        await use_case.authenticate(TOKEN)

    assert store.deleted == [SESSION_ID_HASH]


async def test_database_failure_during_authentication_reaches_the_caller() -> None:
    use_case = AuthenticateSession(
        FakeTransactionRunner(FakeSessionStore(), begin_failure=DatabaseUnavailableError()),
        FakeClock(),
        POLICY,
    )

    with pytest.raises(DatabaseUnavailableError):
        await use_case.authenticate(TOKEN)


async def test_sign_out_deletes_the_session_and_commits() -> None:
    store = store_with_session()
    transactions = FakeTransactionRunner(store)
    session = AuthenticatedSession(SESSION_ID_HASH, STAFF, build_session_account())

    await SignOut(transactions).execute(session)

    assert store.deleted == [SESSION_ID_HASH]
    assert transactions.commit_count == 1


async def test_failure_to_open_the_transaction_of_a_sign_out_reaches_the_caller() -> None:
    transactions = FakeTransactionRunner(
        store_with_session(), begin_failure=DatabaseUnavailableError()
    )
    session = AuthenticatedSession(SESSION_ID_HASH, STAFF, build_session_account())

    with pytest.raises(DatabaseUnavailableError):
        await SignOut(transactions).execute(session)


async def test_failure_to_commit_a_sign_out_reaches_the_caller() -> None:
    transactions = FakeTransactionRunner(
        store_with_session(), commit_failure=DatabaseUnavailableError()
    )
    session = AuthenticatedSession(SESSION_ID_HASH, STAFF, build_session_account())

    with pytest.raises(DatabaseUnavailableError):
        await SignOut(transactions).execute(session)


async def test_require_customer_returns_a_customer() -> None:
    principal = Authorizer(RecordingEventRecorder()).require_customer(
        CUSTOMER, OperationId.LIST_SHOP_ORDERS
    )

    assert principal == CUSTOMER


@pytest.mark.parametrize(
    ("principal", "role"), [(STAFF, "staff"), (MANAGER, "manager"), (ADMIN, "admin")]
)
async def test_require_customer_refuses_every_internal_role(
    principal: Principal, role: str
) -> None:
    events = RecordingEventRecorder()

    with pytest.raises(ForbiddenRoleError):
        Authorizer(events).require_customer(principal, OperationId.GET_SHOP_ORDER)

    (denied,) = events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": principal.account_id,
        "role": role,
        "operation_id": "getShopOrder",
    }


async def test_require_admin_returns_an_admin() -> None:
    principal = Authorizer(RecordingEventRecorder()).require_admin(
        ADMIN, OperationId.LIST_ADMIN_ACCOUNTS
    )

    assert principal == AdminPrincipal(STAFF_ACCOUNT_ID)


@pytest.mark.parametrize(
    ("principal", "role"), [(CUSTOMER, "customer"), (STAFF, "staff"), (MANAGER, "manager")]
)
async def test_require_admin_refuses_every_other_role(principal: Principal, role: str) -> None:
    events = RecordingEventRecorder()

    with pytest.raises(ForbiddenRoleError):
        Authorizer(events).require_admin(principal, OperationId.CHANGE_ACCOUNT_ROLE)

    (denied,) = events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes["role"] == role
