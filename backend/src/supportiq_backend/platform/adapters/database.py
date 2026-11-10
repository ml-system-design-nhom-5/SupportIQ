"""The database engine, the transaction runner, and the mapping of database errors.

Every database call is bounded by the timeout settings (ERR-09): the connect timeout and the
statement timeout on the client side, `statement_timeout` and `lock_timeout` on the server
side, and the pool timeout. Every error of the driver or of SQLAlchemy becomes a domain error
here, so no third-party exception reaches the application layer (ARCH-28).
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg
from sqlalchemy import event, text
from sqlalchemy.engine import ExceptionContext
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from supportiq_backend.platform.domain import (
    MILLISECONDS_PER_SECOND,
    BackendError,
    DatabaseOperationError,
    DatabaseUnavailableError,
    Transaction,
)

APPLICATION_NAME = "supportiq-backend"
# SQLSTATE classes that mean "not available now": 08 connection exception, 53 insufficient
# resources, and 57 operator intervention, which includes 57014 query_canceled, raised by
# statement_timeout (PostgreSQL 17, Appendix A).
_UNAVAILABLE_SQLSTATE_CLASSES = frozenset({"08", "53", "57"})
# Single SQLSTATEs that mean "retry later": 55P03 lock_not_available (lock_timeout),
# 40001 serialization_failure, and 40P01 deadlock_detected.
_UNAVAILABLE_SQLSTATES = frozenset({"55P03", "40001", "40P01"})
_SQLSTATE_CLASS_LENGTH = 2
# Failures of getting a connection that the engine's error handler never sees: the pool
# timeout, socket errors and the connect timeout, and what the server answers to a connection
# attempt, such as too many connections, a restart, or an unknown database. Whatever the
# reason, a replica without a connection is not ready (ERR-18).
_CONNECTION_FAILURES = (PoolTimeoutError, OSError, TimeoutError, asyncpg.PostgresError)


@dataclass(frozen=True, slots=True)
class DatabaseTimeouts:
    """The bounds of every database call, in milliseconds (ERR-09).

    Attributes:
        connect_ms: The longest wait for a new connection.
        statement_ms: The longest run of one statement, on the server and on the client.
        lock_ms: The longest wait for a lock: a row lock, the unique index of the idempotency
            records, or the advisory lock of account changes.
        pool_ms: The longest wait for a free connection of the pool.
    """

    connect_ms: int
    statement_ms: int
    lock_ms: int
    pool_ms: int


def create_database_engine(url: str, timeouts: DatabaseTimeouts) -> AsyncEngine:
    """Create an asyncpg engine whose every call is bounded and whose errors are mapped.

    Args:
        url: A `postgresql+asyncpg://` URL. It holds a password, so it is never logged.
        timeouts: The bounds of every call.

    Returns:
        The engine. The composition root disposes it at shutdown (ARCH-24).
    """
    engine = create_async_engine(
        url,
        pool_timeout=timeouts.pool_ms / MILLISECONDS_PER_SECOND,
        connect_args={
            "timeout": timeouts.connect_ms / MILLISECONDS_PER_SECOND,
            "command_timeout": timeouts.statement_ms / MILLISECONDS_PER_SECOND,
            "server_settings": {
                "statement_timeout": str(timeouts.statement_ms),
                "lock_timeout": str(timeouts.lock_ms),
                "application_name": APPLICATION_NAME,
            },
        },
    )
    event.listen(engine.sync_engine, "handle_error", _to_domain_error, retval=True)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the factory of sessions that the transaction runners use.

    Objects never expire on commit and never flush on their own, so no attribute access
    starts hidden I/O in async code.

    Args:
        engine: The engine from `create_database_engine`.

    Returns:
        The session factory.
    """
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def is_database_unavailable(error: BaseException, *, is_disconnect: bool) -> bool:
    """Tell whether a database error means "not available now" rather than a defect.

    Args:
        error: The error raised by the driver.
        is_disconnect: Whether SQLAlchemy detected a lost connection.

    Returns:
        True for connection failures, timeouts, and lock waits; false for every other error.
    """
    if is_disconnect or isinstance(error, (OSError, TimeoutError)):
        return True
    sqlstate: object = getattr(error, "sqlstate", None)
    if not isinstance(sqlstate, str):
        return False
    return (
        sqlstate in _UNAVAILABLE_SQLSTATES
        or sqlstate[:_SQLSTATE_CLASS_LENGTH] in _UNAVAILABLE_SQLSTATE_CLASSES
    )


class SqlAlchemyTransaction[StoresT]:
    """One open session with its stores; `commit` is the only way to keep its changes."""

    def __init__(self, session: AsyncSession, stores: StoresT) -> None:
        """Bind the stores to the session.

        Args:
            session: The open session.
            stores: The stores built on this session.
        """
        self._session = session
        self._stores = stores

    @property
    def stores(self) -> StoresT:
        """Return the stores bound to this transaction."""
        return self._stores

    async def commit(self) -> None:
        """Commit the transaction; a failure is mapped by the engine's error handler."""
        await self._session.commit()


class SqlAlchemyTransactionRunner[StoresT]:
    """Open one session per transaction and build the stores of a use case on it."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        build_stores: Callable[[AsyncSession], StoresT],
    ) -> None:
        """Keep the factory and the store builder.

        Args:
            session_factory: The factory from `create_session_factory`.
            build_stores: Builds the stores of one use case on an open session. The
                composition root provides it.
        """
        self._session_factory = session_factory
        self._build_stores = build_stores

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[Transaction[StoresT]]:
        """Open a transaction; leaving it without `commit` rolls it back.

        Yields:
            The transaction with its stores.

        Raises:
            DatabaseUnavailableError: No connection was obtained within the pool timeout or
                the connect timeout.
        """
        async with self._session_factory() as session:
            await _acquire_connection(session)
            yield SqlAlchemyTransaction(session, self._build_stores(session))


class DatabaseReadinessProbe:
    """Check that the database answers within the timeouts (ERR-18)."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Keep the engine to check.

        Args:
            engine: The engine of the `backend` replicas.
        """
        self._engine = engine

    async def check(self) -> None:
        """Run one trivial statement.

        Raises:
            DatabaseUnavailableError: The database did not answer within the timeouts.
        """
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except _CONNECTION_FAILURES as error:
            raise DatabaseUnavailableError from error


@asynccontextmanager
async def begin_transaction(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    """Open a connection and a transaction for a one-off command.

    The commands use this instead of `engine.begin()`, which lets a failed connection attempt
    leave the adapters as a third-party exception (ARCH-28).

    Args:
        engine: The engine of the command.

    Yields:
        The connection, in a transaction that commits when the block ends.

    Raises:
        DatabaseUnavailableError: No connection could be opened.
    """
    connection = engine.connect()
    try:
        await connection.start()
    except _CONNECTION_FAILURES as error:
        raise DatabaseUnavailableError from error
    try:
        async with connection.begin():
            yield connection
    finally:
        await connection.close()


async def _acquire_connection(session: AsyncSession) -> None:
    # Taking the connection here, before any store runs, keeps every connection failure inside
    # the adapter (ARCH-28).
    try:
        await session.connection()
    except _CONNECTION_FAILURES as error:
        raise DatabaseUnavailableError from error


def _to_domain_error(context: ExceptionContext) -> BackendError | None:
    # Returned, not raised: a raise would stop the handler chain before the SQLAlchemy
    # instrumentation ends the span of the statement (LOG-22).
    original = context.original_exception
    if not isinstance(original, Exception):
        # Cancellation is no failure of the database, and it must stay what it is (ERR-04).
        return None
    if is_database_unavailable(original, is_disconnect=context.is_disconnect):
        return DatabaseUnavailableError()
    return DatabaseOperationError()
