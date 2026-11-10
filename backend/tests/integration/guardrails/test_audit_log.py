"""Guardrail: the audit log rejects `UPDATE` and `DELETE` (TEST-26, SEC-39)."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.builders import DatabaseBuilder
from tests.integration.database import (
    WorkerDatabase,
    create_owner_engine,
    create_raw_app_engine,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

ENTRY_ID = "00000000-0000-4000-8000-000000000001"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
INSERT_ENTRY = text(
    "INSERT INTO audit_log_entries (entry_id, occurred_at, event_type, trace_id, data) "
    "VALUES (:entry_id, :occurred_at, 'account.role_changed', :trace_id, '{}')"
)
CHANGES = (
    "UPDATE audit_log_entries SET trace_id = 'changed'",
    "DELETE FROM audit_log_entries",
)


async def insert_entry(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            INSERT_ENTRY,
            {"entry_id": ENTRY_ID, "occurred_at": FAKE_CLOCK_START, "trace_id": TRACE_ID},
        )


@pytest.fixture
async def raw_app_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_raw_app_engine(worker_database)
    yield engine
    await engine.dispose()


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


@pytest.mark.parametrize("statement", CHANGES)
async def test_application_role_cannot_change_an_audit_entry(
    raw_app_engine: AsyncEngine, builder: DatabaseBuilder, statement: str
) -> None:
    await insert_entry(raw_app_engine)

    with pytest.raises(DBAPIError, match="permission denied"):
        async with raw_app_engine.begin() as connection:
            await connection.execute(text(statement))

    assert await builder.scalar("SELECT trace_id FROM audit_log_entries") == TRACE_ID


@pytest.mark.parametrize("statement", CHANGES)
async def test_trigger_stops_the_owner_from_changing_an_audit_entry(
    owner_engine: AsyncEngine, builder: DatabaseBuilder, statement: str
) -> None:
    await insert_entry(owner_engine)

    with pytest.raises(DBAPIError, match="audit log entries are never updated or deleted"):
        async with owner_engine.begin() as connection:
            await connection.execute(text(statement))

    assert await builder.scalar("SELECT trace_id FROM audit_log_entries") == TRACE_ID
