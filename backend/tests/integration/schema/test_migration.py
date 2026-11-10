"""The first migration: it upgrades, downgrades completely, and upgrades again (PY-40).

The downgrade runs on a database of its own, so no other test sees a schema without tables.
"""

from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from supportiq_backend.accounts.adapters.tables import AccountsTables
from supportiq_backend.audit.adapters.tables import AuditTables
from supportiq_backend.commerce.adapters.tables import CommerceTables
from supportiq_backend.idempotency.adapters.tables import IdempotencyTables
from supportiq_backend.migrations.tables import TRUNCATE_EVERY_TABLE
from supportiq_backend.platform import BackendError
from supportiq_backend.platform.adapters.migrations import (
    HEAD,
    SCRIPT_LOCATION,
    downgrade_database,
    head_revision,
    upgrade_database,
)
from supportiq_backend.tickets.adapters.tables import TicketsTables
from tests.integration.database import (
    BACKEND_TABLE_NAMES,
    WorkerDatabase,
    create_owner_engine,
    drop_database,
    recreate_database,
)

pytestmark = pytest.mark.anyio

FEATURE_TABLES: tuple[type[DeclarativeBase], ...] = (
    AccountsTables,
    AuditTables,
    CommerceTables,
    IdempotencyTables,
    TicketsTables,
)
SCHEMA_OBJECTS = text(
    "SELECT (SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
    " AND tablename <> 'alembic_version'),"
    " (SELECT count(*) FROM pg_proc WHERE proname LIKE 'reject_%'),"
    " (SELECT count(*) FROM pg_class WHERE relname = 'ticket_number_seq'),"
    # The grant of the migration itself; PUBLIC keeps its own default USAGE on `public`.
    " EXISTS (SELECT FROM pg_namespace, aclexplode(nspacl) AS acl"
    " WHERE nspname = 'public' AND acl.grantee = 'supportiq_app'::regrole)"
)


def table_columns(connection: Connection) -> dict[str, dict[str, bool]]:
    inspector = inspect(connection)
    return {
        table: {column["name"]: column["nullable"] for column in inspector.get_columns(table)}
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


def orm_columns() -> dict[str, dict[str, bool]]:
    return {
        table.name: {column.name: bool(column.nullable) for column in table.columns}
        for base in FEATURE_TABLES
        for table in base.metadata.sorted_tables
    }


@pytest.fixture
async def migration_database(worker_database: WorkerDatabase) -> AsyncIterator[WorkerDatabase]:
    name = worker_database.name + "_migration"
    database = replace(
        worker_database,
        name=name,
        owner_url=make_url(worker_database.owner_url)
        .set(database=name)
        .render_as_string(hide_password=False),
    )
    await recreate_database(database)
    yield database
    await drop_database(database)


@pytest.fixture
async def migration_engine(migration_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(migration_database)
    yield engine
    await engine.dispose()


def test_alembic_without_the_connection_of_backend_migrate_is_refused() -> None:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)

    with pytest.raises(BackendError):
        command.upgrade(config, HEAD)


async def test_upgrade_reaches_the_head_revision(migration_engine: AsyncEngine) -> None:
    revision = await upgrade_database(migration_engine)

    assert revision == head_revision() == "0001"


async def test_downgrade_removes_every_object_of_the_upgrade(
    migration_engine: AsyncEngine,
) -> None:
    await upgrade_database(migration_engine)

    revision = await downgrade_database(migration_engine)
    async with migration_engine.connect() as connection:
        objects = (await connection.execute(SCHEMA_OBJECTS)).one()

    assert revision is None
    assert tuple(objects) == (0, 0, 0, False)


async def test_upgrade_after_a_downgrade_restores_the_schema(
    migration_engine: AsyncEngine,
) -> None:
    await upgrade_database(migration_engine)
    await downgrade_database(migration_engine)

    revision = await upgrade_database(migration_engine)
    async with migration_engine.connect() as connection:
        objects = (await connection.execute(SCHEMA_OBJECTS)).one()

    assert revision == "0001"
    assert tuple(objects) == (len(BACKEND_TABLE_NAMES), 3, 1, True)


async def test_migrated_tables_are_exactly_the_tables_that_reset_truncates(
    worker_database: WorkerDatabase,
) -> None:
    engine = create_async_engine(worker_database.owner_url)
    async with engine.connect() as connection:
        columns = await connection.run_sync(table_columns)
    await engine.dispose()

    assert set(columns) == set(BACKEND_TABLE_NAMES)


def test_the_truncate_statement_lists_every_table() -> None:
    table_list = ", ".join(BACKEND_TABLE_NAMES)

    assert f"TRUNCATE TABLE {table_list} RESTART IDENTITY" == TRUNCATE_EVERY_TABLE


async def test_orm_models_of_the_features_match_the_migrated_columns(
    worker_database: WorkerDatabase,
) -> None:
    engine = create_async_engine(worker_database.owner_url)
    async with engine.connect() as connection:
        columns = await connection.run_sync(table_columns)
    await engine.dispose()

    assert columns == orm_columns()
