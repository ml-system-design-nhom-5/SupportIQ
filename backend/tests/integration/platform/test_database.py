"""Integration tests of the database adapter: every call is bounded and every error is mapped.

The timeouts are shortened to tens of milliseconds, so each test waits only for the bound it
proves (ERR-09, ERR-21). No test sleeps on its own.
"""

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from supportiq_backend.platform import (
    MILLISECONDS_PER_SECOND,
    DatabaseOperationError,
    DatabaseUnavailableError,
)
from supportiq_backend.platform.adapters.database import (
    DatabaseReadinessProbe,
    DatabaseTimeouts,
    SqlAlchemyTransactionRunner,
    begin_transaction,
    create_database_engine,
    create_session_factory,
)
from tests.integration.database import DESIGN_TIMEOUTS, WorkerDatabase, create_owner_engine

pytestmark = pytest.mark.anyio

SHORT_MS = 50
LOCK_KEY = 4_242
LOOPBACK = "127.0.0.1"
# SQLAlchemy's default pool: 5 connections plus an overflow of 10.
POOL_CAPACITY = 15
UNKNOWN_DATABASE = "supportiq_no_such_database"
LIMITED_PASSWORD = "limited-test-password"


def build_engine(url: str, **timeouts_ms: int) -> AsyncEngine:
    defaults = {
        "connect_ms": DESIGN_TIMEOUTS.connect_ms,
        "statement_ms": DESIGN_TIMEOUTS.statement_ms,
        "lock_ms": DESIGN_TIMEOUTS.lock_ms,
        "pool_ms": DESIGN_TIMEOUTS.pool_ms,
    }
    return create_database_engine(url, DatabaseTimeouts(**(defaults | timeouts_ms)), ca_file=None)


def session_runner(engine: AsyncEngine) -> SqlAlchemyTransactionRunner[AsyncSession]:
    return SqlAlchemyTransactionRunner(create_session_factory(engine), lambda session: session)


def url_with_port(url: str, port: int) -> str:
    return make_url(url).set(host=LOOPBACK, port=port).render_as_string(hide_password=False)


async def hold_every_pool_connection(
    held: AsyncExitStack, runner: SqlAlchemyTransactionRunner[AsyncSession]
) -> None:
    await asyncio.gather(*(held.enter_async_context(runner.begin()) for _ in range(POOL_CAPACITY)))


async def lose_the_connection_in_a_transaction(
    engine: AsyncEngine, other_engine: AsyncEngine
) -> None:
    async with session_runner(engine).begin() as transaction:
        backend_id = await transaction.stores.scalar(text("SELECT pg_backend_pid()"))
        async with other_engine.connect() as connection:
            await connection.execute(
                text("SELECT pg_terminate_backend(:backend_id, :wait_ms)"),
                {"backend_id": backend_id, "wait_ms": DESIGN_TIMEOUTS.lock_ms},
            )
        await transaction.stores.execute(text("SELECT 1"))


async def run_a_long_statement_with_a_short_timeout(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        async with asyncio.timeout(SHORT_MS / MILLISECONDS_PER_SECOND):
            await connection.execute(text("SELECT pg_sleep(60)"))


@pytest.fixture
def closed_port_url(worker_database: WorkerDatabase) -> str:
    with socket.socket() as probe:
        probe.bind((LOOPBACK, 0))
        port = int(probe.getsockname()[1])
    return url_with_port(worker_database.app_url, port)


@pytest.fixture
def unknown_database_url(worker_database: WorkerDatabase) -> str:
    """Return a URL that PostgreSQL refuses with SQLSTATE 3D000, invalid_catalog_name."""
    url = make_url(worker_database.app_url).set(database=UNKNOWN_DATABASE)
    return url.render_as_string(hide_password=False)


@pytest.fixture
async def connection_limit_url(worker_database: WorkerDatabase) -> AsyncIterator[str]:
    """Return a URL that PostgreSQL refuses with SQLSTATE 53300, too_many_connections."""
    role = f"{worker_database.name}_no_connections"
    owner = create_owner_engine(worker_database)
    async with owner.begin() as connection:
        await connection.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        await connection.execute(
            text(f"""CREATE ROLE "{role}" LOGIN CONNECTION LIMIT 0 PASSWORD '{LIMITED_PASSWORD}'""")
        )
    url = make_url(worker_database.app_url).set(username=role, password=LIMITED_PASSWORD)
    yield url.render_as_string(hide_password=False)
    async with owner.begin() as connection:
        await connection.execute(text(f'DROP ROLE "{role}"'))
    await owner.dispose()


@pytest.fixture
async def silent_server_url(worker_database: WorkerDatabase) -> AsyncIterator[str]:
    async def accept_and_never_answer(
        _reader: asyncio.StreamReader, _writer: asyncio.StreamWriter
    ) -> None:
        await asyncio.Event().wait()

    server = await asyncio.start_server(accept_and_never_answer, LOOPBACK, 0)
    port = int(server.sockets[0].getsockname()[1])
    yield url_with_port(worker_database.app_url, port)
    server.close()


async def test_transaction_runs_statements_as_supportiq_app(app_engine: AsyncEngine) -> None:
    async with session_runner(app_engine).begin() as transaction:
        role = await transaction.stores.scalar(text("SELECT current_user"))

    assert role == "supportiq_app"


async def test_engine_sets_the_server_side_timeouts_of_the_settings(
    worker_database: WorkerDatabase,
) -> None:
    engine = build_engine(worker_database.app_url, statement_ms=1_234, lock_ms=567)

    async with session_runner(engine).begin() as transaction:
        statement_timeout = await transaction.stores.scalar(text("SHOW statement_timeout"))
        lock_timeout = await transaction.stores.scalar(text("SHOW lock_timeout"))

    assert (statement_timeout, lock_timeout) == ("1234ms", "567ms")
    await engine.dispose()


async def test_statement_timeout_becomes_database_unavailable(
    worker_database: WorkerDatabase,
) -> None:
    engine = build_engine(worker_database.app_url, statement_ms=SHORT_MS)

    with pytest.raises(DatabaseUnavailableError):
        async with session_runner(engine).begin() as transaction:
            await transaction.stores.execute(text("SELECT pg_sleep(5)"))

    await engine.dispose()


async def test_lock_timeout_becomes_database_unavailable(
    worker_database: WorkerDatabase, app_engine: AsyncEngine
) -> None:
    waiting_engine = build_engine(worker_database.app_url, lock_ms=SHORT_MS)
    lock = text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=LOCK_KEY)

    async with session_runner(app_engine).begin() as holder:
        await holder.stores.execute(lock)
        with pytest.raises(DatabaseUnavailableError):
            async with session_runner(waiting_engine).begin() as waiter:
                await waiter.stores.execute(lock)

    await waiting_engine.dispose()


async def test_pool_timeout_becomes_database_unavailable(worker_database: WorkerDatabase) -> None:
    engine = build_engine(worker_database.app_url, pool_ms=SHORT_MS)
    runner = session_runner(engine)

    async with AsyncExitStack() as held:
        await hold_every_pool_connection(held, runner)
        with pytest.raises(DatabaseUnavailableError):
            await held.enter_async_context(runner.begin())

    await engine.dispose()


async def test_refused_connection_becomes_database_unavailable(closed_port_url: str) -> None:
    engine = build_engine(closed_port_url)

    with pytest.raises(DatabaseUnavailableError):
        await AsyncExitStack().enter_async_context(session_runner(engine).begin())

    await engine.dispose()


async def test_database_that_postgresql_refuses_becomes_database_unavailable(
    unknown_database_url: str,
) -> None:
    engine = build_engine(unknown_database_url)

    with pytest.raises(DatabaseUnavailableError):
        await AsyncExitStack().enter_async_context(session_runner(engine).begin())

    await engine.dispose()


async def test_connection_limit_becomes_database_unavailable(connection_limit_url: str) -> None:
    engine = build_engine(connection_limit_url)

    with pytest.raises(DatabaseUnavailableError):
        await AsyncExitStack().enter_async_context(session_runner(engine).begin())

    await engine.dispose()


async def test_readiness_probe_fails_when_postgresql_refuses_the_connection(
    unknown_database_url: str,
) -> None:
    engine = build_engine(unknown_database_url)

    with pytest.raises(DatabaseUnavailableError):
        await DatabaseReadinessProbe(engine).check()

    await engine.dispose()


async def test_transaction_of_a_command_maps_a_refused_connection(closed_port_url: str) -> None:
    engine = build_engine(closed_port_url)

    with pytest.raises(DatabaseUnavailableError):
        await AsyncExitStack().enter_async_context(begin_transaction(engine))

    await engine.dispose()


async def test_transaction_of_a_command_maps_what_postgresql_refuses(
    unknown_database_url: str,
) -> None:
    engine = build_engine(unknown_database_url)

    with pytest.raises(DatabaseUnavailableError):
        await AsyncExitStack().enter_async_context(begin_transaction(engine))

    await engine.dispose()


async def test_transaction_of_a_command_commits_when_the_block_ends(
    worker_database: WorkerDatabase,
) -> None:
    engine = create_owner_engine(worker_database)

    async with begin_transaction(engine) as connection:
        await connection.execute(text("COMMENT ON TABLE tickets IS 'supportiq_test_committed'"))
    async with begin_transaction(engine) as connection:
        comment = await connection.scalar(text("SELECT obj_description('tickets'::regclass)"))
        await connection.execute(text("COMMENT ON TABLE tickets IS NULL"))

    await engine.dispose()
    assert comment == "supportiq_test_committed"


async def test_connection_lost_in_a_transaction_becomes_database_unavailable(
    worker_database: WorkerDatabase,
) -> None:
    engine = build_engine(worker_database.owner_url)
    other_engine = build_engine(worker_database.owner_url)

    with pytest.raises(DatabaseUnavailableError):
        await lose_the_connection_in_a_transaction(engine, other_engine)

    await other_engine.dispose()
    await engine.dispose()


async def test_cancellation_of_a_statement_stays_a_cancellation(
    worker_database: WorkerDatabase,
) -> None:
    engine = build_engine(worker_database.owner_url)

    # `asyncio.timeout` turns only a cancellation into `TimeoutError`, so any other error here
    # means that the adapter replaced the cancellation.
    with pytest.raises(TimeoutError):
        await run_a_long_statement_with_a_short_timeout(engine)

    await engine.dispose()


async def test_connect_timeout_becomes_database_unavailable(silent_server_url: str) -> None:
    engine = build_engine(silent_server_url, connect_ms=SHORT_MS)

    with pytest.raises(DatabaseUnavailableError):
        await AsyncExitStack().enter_async_context(session_runner(engine).begin())

    await engine.dispose()


async def test_statement_error_becomes_database_operation_error(app_engine: AsyncEngine) -> None:
    with pytest.raises(DatabaseOperationError):
        async with session_runner(app_engine).begin() as transaction:
            await transaction.stores.execute(text("SELECT 1 / 0"))


async def test_statement_without_privilege_becomes_database_operation_error(
    app_engine: AsyncEngine,
) -> None:
    with pytest.raises(DatabaseOperationError):
        async with session_runner(app_engine).begin() as transaction:
            await transaction.stores.execute(text("CREATE TABLE public.intruder (id integer)"))


async def test_readiness_probe_fails_when_the_database_is_unreachable(
    closed_port_url: str,
) -> None:
    engine = build_engine(closed_port_url)

    with pytest.raises(DatabaseUnavailableError):
        await DatabaseReadinessProbe(engine).check()

    await engine.dispose()
