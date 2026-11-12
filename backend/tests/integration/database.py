"""One isolated PostgreSQL database per test worker (TEST-15, TEST-17).

Each pytest-xdist worker drops and creates its own database `supportiq_test_<worker>`, as the
owner, and migrates it. Tests connect as `supportiq_app` with the privileges of the design,
never as the owner, so every test also proves those privileges. Only setup and cleanup use the
owner, because `supportiq_app` cannot insert admin accounts, customer accounts, or commerce data.

The role `supportiq_app` must exist first: `backend create-app-role` creates it once per
cluster (README.md, Set up). The URLs come from the environment variables `DATABASE_URL_OWNER`
and `DATABASE_URL_APP`, the same as the settings of backend.
"""

import re
from dataclasses import dataclass, field

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from supportiq_backend.migrations.tables import TRUNCATE_EVERY_TABLE
from supportiq_backend.platform.adapters.database import DatabaseTimeouts
from supportiq_backend.platform.adapters.migrations import upgrade_database

MAINTENANCE_DATABASE = "postgres"
TEST_DATABASE_PREFIX = "supportiq_test_"
_WORKER_ID_PATTERN = re.compile(r"gw[0-9]+|master")
# The tables of the migrated schema, the expected value of the schema and seed tests.
BACKEND_TABLE_NAMES = (
    "accounts",
    "sessions",
    "sign_in_failures",
    "idempotency_records",
    "customers",
    "products",
    "orders",
    "order_lines",
    "shipments",
    "refunds",
    "tickets",
    "customer_messages",
    "audit_log_entries",
)
# The timeouts of the design's Settings table.
DESIGN_TIMEOUTS = DatabaseTimeouts(
    connect_ms=3_000, statement_ms=5_000, lock_ms=3_000, pool_ms=3_000
)


class IntegrationDatabaseSettings(BaseSettings):
    """The two connection strings that the integration tests need."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", frozen=True)

    database_url_owner: SecretStr
    database_url_app: SecretStr


class UnknownWorkerError(Exception):
    """The pytest-xdist worker ID does not have the expected form."""

    def __init__(self) -> None:
        """Build the error."""
        super().__init__("The test worker ID must be gw<number> or master")


@dataclass(frozen=True, slots=True)
class WorkerDatabase:
    """The database of one test worker.

    The URLs hold passwords, so they stay out of the `repr` that pytest prints (PY-44).

    Attributes:
        name: The database name, `supportiq_test_<worker>`.
        owner_url: The URL that connects as the owner.
        app_url: The URL that connects as `supportiq_app`.
        maintenance_url: The URL of the `postgres` database, as the owner.
    """

    name: str
    owner_url: str = field(repr=False)
    app_url: str = field(repr=False)
    maintenance_url: str = field(repr=False)


def load_test_database(worker_id: str) -> WorkerDatabase:
    """Describe the database of a worker from the environment.

    Args:
        worker_id: The pytest-xdist worker ID, such as `gw0`, or `master` without workers.

    Returns:
        The database of the worker. Nothing is created yet.

    Raises:
        UnknownWorkerError: The worker ID cannot be part of a database name.
    """
    if _WORKER_ID_PATTERN.fullmatch(worker_id) is None:
        raise UnknownWorkerError
    # A settings class reads its values from the environment during validation.
    settings = IntegrationDatabaseSettings.model_validate({})
    name = TEST_DATABASE_PREFIX + worker_id
    owner = make_url(settings.database_url_owner.get_secret_value())
    app = make_url(settings.database_url_app.get_secret_value())
    return WorkerDatabase(
        name=name,
        owner_url=owner.set(database=name).render_as_string(hide_password=False),
        app_url=app.set(database=name).render_as_string(hide_password=False),
        maintenance_url=owner.set(database=MAINTENANCE_DATABASE).render_as_string(
            hide_password=False
        ),
    )


async def recreate_database(database: WorkerDatabase) -> None:
    """Drop the database of the worker if it exists, then create it empty.

    Args:
        database: The database of the worker.
    """
    await _run_on_maintenance_database(
        database, _drop_statement(database), _create_statement(database)
    )


async def drop_database(database: WorkerDatabase) -> None:
    """Drop the database of the worker at the end of the session.

    Args:
        database: The database of the worker.
    """
    await _run_on_maintenance_database(database, _drop_statement(database))


async def _run_on_maintenance_database(database: WorkerDatabase, *statements: str) -> None:
    engine = create_async_engine(database.maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


def _drop_statement(database: WorkerDatabase) -> str:
    # The name is a worker name checked against `supportiq_test_(gw<number>|master)`, or that
    # name with the constant suffix `_migration` of the migration test, so it needs no quoting
    # beyond the identifier quotes; identifiers cannot be bound parameters (PY-42). WITH (FORCE)
    # fails for a role without superuser when an autovacuum worker is in the database, and a
    # plain DROP DATABASE stops that worker by itself.
    return f'DROP DATABASE IF EXISTS "{database.name}"'


def _create_statement(database: WorkerDatabase) -> str:
    return f'CREATE DATABASE "{database.name}"'


def create_owner_engine(database: WorkerDatabase) -> AsyncEngine:
    """Create an engine that connects to the worker database as the owner, for setup only.

    Args:
        database: The database of the worker.

    Returns:
        The engine; the caller disposes it.
    """
    return create_async_engine(database.owner_url)


def create_raw_app_engine(database: WorkerDatabase) -> AsyncEngine:
    """Create an engine as `supportiq_app` without the error mapping of backend.

    Privilege and trigger tests use it to see the SQLSTATE that PostgreSQL returns.

    Args:
        database: The database of the worker.

    Returns:
        The engine; the caller disposes it.
    """
    return create_async_engine(database.app_url)


async def migrate_database(database: WorkerDatabase) -> None:
    """Apply every migration to the database of the worker, as the owner.

    Args:
        database: The database of the worker.
    """
    engine = create_owner_engine(database)
    try:
        await upgrade_database(engine)
    finally:
        await engine.dispose()


async def empty_every_table(database: WorkerDatabase) -> None:
    """Remove every row and restart the ticket numbers, as the reset command does.

    Args:
        database: The database of the worker.
    """
    engine = create_owner_engine(database)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(TRUNCATE_EVERY_TABLE))
    finally:
        await engine.dispose()
