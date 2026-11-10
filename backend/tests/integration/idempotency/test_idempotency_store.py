"""Integration tests of `PostgresIdempotencyStore`: the unique key, its waits, and expiry.

Two requests with one key run on two connections. Whatever the timing, the second one either
waits on the unique index until the first ends or finds its committed record, so the assertions
need no sleep (TEST-14).
"""

import asyncio
from collections.abc import AsyncIterator, Mapping
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from supportiq_backend.idempotency import (
    ClaimOutcome,
    ExistingRecord,
    IdempotencyGuard,
    IdempotencyKey,
    IdempotencyKeyReusedError,
    IdempotentRequest,
    NewRequest,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.idempotency.adapters.idempotency_store import PostgresIdempotencyStore
from supportiq_backend.platform import (
    MILLISECONDS_PER_SECOND,
    DatabaseUnavailableError,
    OperationId,
    TransactionRunner,
)
from supportiq_backend.platform.adapters.database import (
    DatabaseTimeouts,
    SqlAlchemyTransactionRunner,
    create_database_engine,
    create_session_factory,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import DESIGN_TIMEOUTS, WorkerDatabase, create_owner_engine
from tests.unit.platform.fakes import FakeClock

pytestmark = pytest.mark.anyio

KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000001"))
RETENTION_MS = 86_400_000
SHORT_LOCK_MS = 50
# Not the output of any serializer: the store keeps the text exactly as given.
EXACT_BODY = '{ "ticket_id" :  "TCK-1001",\n  "message": "Đơn hàng của tôi" }'
RESPONSE = StoredResponse(201, EXACT_BODY)
SKIP_INSERT_FUNCTION = """
    CREATE FUNCTION skip_insert_for_test() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RETURN NULL;
    END
    $$
"""
SKIP_INSERT_TRIGGER = """
    CREATE TRIGGER skip_insert_for_test BEFORE INSERT ON idempotency_records
        FOR EACH ROW EXECUTE FUNCTION skip_insert_for_test()
"""

type StoreRunner = TransactionRunner[PostgresIdempotencyStore]


def store_runner(engine: AsyncEngine) -> StoreRunner:
    return SqlAlchemyTransactionRunner(create_session_factory(engine), build_store)


def build_store(session: AsyncSession) -> PostgresIdempotencyStore:
    return PostgresIdempotencyStore(session)


def build_request(
    account_id: UUID,
    *,
    request: Mapping[str, str] | None = None,
    operation: OperationId = OperationId.CREATE_SHOP_TICKET,
) -> IdempotentRequest:
    return build_idempotent_request(
        RequesterId(str(account_id)), operation, KEY, request or {"message": "Hi"}
    )


async def claim(
    runner: StoreRunner, guard: IdempotencyGuard, request: IdempotentRequest
) -> ClaimOutcome:
    async with runner.begin() as transaction:
        outcome = await guard.claim(transaction.stores, request)
        await transaction.commit()
    return outcome


async def complete(
    runner: StoreRunner, guard: IdempotencyGuard, request: IdempotentRequest
) -> None:
    async with runner.begin() as transaction:
        await guard.claim(transaction.stores, request)
        await transaction.stores.save_response(request, RESPONSE)
        await transaction.commit()


@pytest.fixture
def guard() -> IdempotencyGuard:
    return IdempotencyGuard(FakeClock(), RETENTION_MS)


@pytest.fixture
async def account_id(builder: DatabaseBuilder) -> UUID:
    return await builder.account(AccountSpec("staff"))


async def test_first_claim_inserts_a_record_without_a_response(
    app_engine: AsyncEngine, builder: DatabaseBuilder, guard: IdempotencyGuard, account_id: UUID
) -> None:
    outcome = await claim(store_runner(app_engine), guard, build_request(account_id))

    assert outcome == NewRequest()
    assert await builder.scalar("SELECT count(*) FROM idempotency_records") == 1
    assert await builder.scalar("SELECT response_status FROM idempotency_records") is None


async def test_repeat_returns_the_exact_text_of_the_first_response(
    app_engine: AsyncEngine, guard: IdempotencyGuard, account_id: UUID
) -> None:
    runner = store_runner(app_engine)
    await complete(runner, guard, build_request(account_id))

    outcome = await claim(runner, guard, build_request(account_id))

    assert outcome == RepeatedRequest(RESPONSE)
    assert isinstance(outcome, RepeatedRequest)
    assert outcome.response.body == EXACT_BODY


async def test_same_key_with_another_request_is_refused(
    app_engine: AsyncEngine, guard: IdempotencyGuard, account_id: UUID
) -> None:
    runner = store_runner(app_engine)
    await complete(runner, guard, build_request(account_id))

    with pytest.raises(IdempotencyKeyReusedError):
        await claim(runner, guard, build_request(account_id, request={"message": "Hello"}))


async def test_key_belongs_to_one_account(
    app_engine: AsyncEngine, builder: DatabaseBuilder, guard: IdempotencyGuard, account_id: UUID
) -> None:
    runner = store_runner(app_engine)
    await complete(runner, guard, build_request(account_id))
    other_account_id = await builder.account(AccountSpec("staff"))

    outcome = await claim(runner, guard, build_request(other_account_id))

    assert outcome == NewRequest()


async def test_key_belongs_to_one_operation(
    app_engine: AsyncEngine, guard: IdempotencyGuard, account_id: UUID
) -> None:
    runner = store_runner(app_engine)
    await complete(runner, guard, build_request(account_id))

    outcome = await claim(
        runner,
        guard,
        build_request(account_id, operation=OperationId.CHANGE_ACCOUNT_ROLE),
    )

    assert outcome == NewRequest()


async def test_rolled_back_claim_leaves_no_record(
    app_engine: AsyncEngine, builder: DatabaseBuilder, guard: IdempotencyGuard, account_id: UUID
) -> None:
    async with store_runner(app_engine).begin() as transaction:
        await guard.claim(transaction.stores, build_request(account_id))

    assert await builder.scalar("SELECT count(*) FROM idempotency_records") == 0


async def test_second_request_waits_and_returns_the_response_of_the_first(
    app_engine: AsyncEngine, guard: IdempotencyGuard, account_id: UUID
) -> None:
    runner = store_runner(app_engine)
    request = build_request(account_id)

    async with runner.begin() as first:
        await guard.claim(first.stores, request)
        second = asyncio.create_task(claim(runner, guard, request))
        await first.stores.save_response(request, RESPONSE)
        await first.commit()

    assert await second == RepeatedRequest(RESPONSE)


async def test_second_request_runs_as_new_when_the_first_rolls_back(
    app_engine: AsyncEngine, guard: IdempotencyGuard, account_id: UUID
) -> None:
    runner = store_runner(app_engine)
    request = build_request(account_id)

    async with runner.begin() as first:
        await guard.claim(first.stores, request)
        second = asyncio.create_task(claim(runner, guard, request))

    assert await second == NewRequest()


@pytest.fixture
async def insert_skipped_by_a_trigger(worker_database: WorkerDatabase) -> AsyncIterator[None]:
    """Make an insert that conflicts with nothing come back empty, as if a cleanup had raced."""
    engine = create_owner_engine(worker_database)
    async with engine.begin() as connection:
        await connection.execute(text(SKIP_INSERT_FUNCTION))
        await connection.execute(text(SKIP_INSERT_TRIGGER))
    yield
    async with engine.begin() as connection:
        await connection.execute(text("DROP FUNCTION skip_insert_for_test CASCADE"))
    await engine.dispose()


@pytest.mark.usefixtures("insert_skipped_by_a_trigger")
async def test_record_that_vanishes_after_the_conflict_becomes_database_unavailable(
    app_engine: AsyncEngine, guard: IdempotencyGuard, account_id: UUID
) -> None:
    runner = store_runner(app_engine)

    with pytest.raises(DatabaseUnavailableError):
        await claim(runner, guard, build_request(account_id))


async def test_wait_longer_than_the_lock_timeout_becomes_database_unavailable(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    guard: IdempotencyGuard,
    account_id: UUID,
) -> None:
    waiting_engine = create_database_engine(
        worker_database.app_url,
        DatabaseTimeouts(
            connect_ms=DESIGN_TIMEOUTS.connect_ms,
            statement_ms=DESIGN_TIMEOUTS.statement_ms,
            lock_ms=SHORT_LOCK_MS,
            pool_ms=DESIGN_TIMEOUTS.pool_ms,
        ),
    )
    request = build_request(account_id)

    async with store_runner(app_engine).begin() as first:
        await guard.claim(first.stores, request)
        with pytest.raises(DatabaseUnavailableError):
            await claim(store_runner(waiting_engine), guard, request)

    await waiting_engine.dispose()


async def test_record_exactly_at_the_retention_is_kept(
    app_engine: AsyncEngine, account_id: UUID
) -> None:
    clock = FakeClock()
    guard = IdempotencyGuard(clock, RETENTION_MS)
    runner = store_runner(app_engine)
    await complete(runner, guard, build_request(account_id))

    clock.advance(RETENTION_MS)
    outcome = await claim(runner, guard, build_request(account_id))

    assert outcome == RepeatedRequest(RESPONSE)


async def test_expired_record_is_deleted_and_its_key_runs_as_new(
    app_engine: AsyncEngine, builder: DatabaseBuilder, account_id: UUID
) -> None:
    clock = FakeClock()
    guard = IdempotencyGuard(clock, RETENTION_MS)
    runner = store_runner(app_engine)
    await complete(runner, guard, build_request(account_id))

    clock.advance(RETENTION_MS + 1)
    outcome = await claim(runner, guard, build_request(account_id, request={"message": "Hello"}))

    assert outcome == NewRequest()
    assert await builder.scalar("SELECT count(*) FROM idempotency_records") == 1


async def test_claim_deletes_expired_records_of_other_keys(
    app_engine: AsyncEngine, builder: DatabaseBuilder, account_id: UUID
) -> None:
    clock = FakeClock()
    guard = IdempotencyGuard(clock, RETENTION_MS)
    runner = store_runner(app_engine)
    await complete(runner, guard, build_request(account_id))
    other_account_id = await builder.account(AccountSpec("staff"))

    clock.advance(int(timedelta(days=2).total_seconds() * MILLISECONDS_PER_SECOND))
    await claim(runner, guard, build_request(other_account_id))

    assert await builder.scalar("SELECT count(*) FROM idempotency_records") == 1


async def test_record_without_a_response_of_a_committed_claim_is_seen_as_incomplete(
    app_engine: AsyncEngine, guard: IdempotencyGuard, account_id: UUID
) -> None:
    runner = store_runner(app_engine)
    request = build_request(account_id)
    await claim(runner, guard, request)

    async with runner.begin() as transaction:
        now = FakeClock().now()
        outcome = await transaction.stores.claim(request, now=now, expired_before=now)

    assert outcome == ExistingRecord(request.request_hash, None)
