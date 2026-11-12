"""Adapter tests of `PostgresPseudonymMapStore` against PostgreSQL 17 (TEST-01).

A ticket's map is inserted in one transaction and never updated: a row already stored for the
same pseudonym stays as it was, and `supportiq_app` can neither update nor delete a row
(ADR-0010, Storage and lifecycle, items 2 and 3). The original values are synthetic (TEST-18).
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.platform.adapters.database import create_session_factory
from supportiq_backend.pseudonymization.adapters.pseudonym_map_store import (
    PostgresPseudonymMapStore,
)
from supportiq_backend.pseudonymization.domain import MapTicketId, PseudonymEntry, PseudonymType
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_raw_app_engine
from tests.integration.schema.statements import INSUFFICIENT_PRIVILEGE, sqlstate_of_refusal
from tests.integration.workflow.workflow_rows import insert_ticket, wait_until_row_lock_waits
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

NOW = FAKE_CLOCK_START
LATER = FAKE_CLOCK_START + timedelta(minutes=5)
ADDRESS = PseudonymEntry("[ADDRESS_1]", PseudonymType.ADDRESS, "12 Example Street, Hanoi")
EMAIL = PseudonymEntry("[EMAIL_1]", PseudonymType.EMAIL, "lan.tran@example.test")
NAME = PseudonymEntry("[NAME_1]", PseudonymType.NAME, "Lan Tran")
PHONE = PseudonymEntry("[PHONE_1]", PseudonymType.PHONE, "+84 90 000 0001")
# The same pseudonym for another spelling, as a run with a different map would compute it.
OTHER_NAME = PseudonymEntry("[NAME_1]", PseudonymType.NAME, "Lan")
NAME_CREATED_AT = "SELECT created_at FROM pseudonym_map_entries WHERE pseudonym = '[NAME_1]'"


@pytest.fixture
async def app_engine_raw(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_raw_app_engine(worker_database)
    yield engine
    await engine.dispose()


async def insert_map(
    engine: AsyncEngine, ticket_id: MapTicketId, entries: tuple[PseudonymEntry, ...]
) -> None:
    async with create_session_factory(engine)() as session:
        await PostgresPseudonymMapStore(session).insert_map(ticket_id, entries, NOW)
        await session.commit()


async def load_entries(engine: AsyncEngine, ticket_id: MapTicketId) -> tuple[PseudonymEntry, ...]:
    async with create_session_factory(engine)() as session:
        return await PostgresPseudonymMapStore(session).load_entries(ticket_id)


async def insert_and_load(
    engine: AsyncEngine, ticket_id: MapTicketId, entries: tuple[PseudonymEntry, ...]
) -> tuple[PseudonymEntry, ...]:
    # A first run of pseudonymization: insert the map, read it back, and commit.
    async with create_session_factory(engine)() as session:
        store = PostgresPseudonymMapStore(session)
        await store.insert_map(ticket_id, entries, LATER)
        stored = await store.load_entries(ticket_id)
        await session.commit()
    return stored


async def new_ticket(builder: DatabaseBuilder) -> MapTicketId:
    return MapTicketId(await insert_ticket(builder))


async def test_insert_map_then_load_entries_returns_them_ordered_by_pseudonym(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await new_ticket(builder)

    await insert_map(app_engine, ticket_id, (PHONE, NAME, EMAIL, ADDRESS))

    assert await load_entries(app_engine, ticket_id) == (ADDRESS, EMAIL, NAME, PHONE)


async def test_load_entries_of_a_ticket_without_a_map_is_empty(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await new_ticket(builder)

    assert await load_entries(app_engine, ticket_id) == ()


async def test_load_entries_returns_only_the_map_of_the_ticket(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await new_ticket(builder)
    other_ticket_id = await new_ticket(builder)
    await insert_map(app_engine, ticket_id, (NAME,))
    await insert_map(app_engine, other_ticket_id, (EMAIL,))

    entries = await load_entries(app_engine, ticket_id)

    assert entries == (NAME,)


async def test_insert_map_keeps_a_row_already_stored_for_the_same_pseudonym(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await new_ticket(builder)
    await insert_map(app_engine, ticket_id, (EMAIL, NAME))

    stored = await insert_and_load(app_engine, ticket_id, (OTHER_NAME, PHONE))

    assert stored == (EMAIL, NAME, PHONE)
    assert await builder.scalar(NAME_CREATED_AT) == NOW


async def test_insert_map_of_no_entries_stores_nothing(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await new_ticket(builder)

    await insert_map(app_engine, ticket_id, ())

    assert await builder.scalar("SELECT count(*) FROM pseudonym_map_entries") == 0


async def test_insert_map_of_a_rolled_back_run_keeps_no_row(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await new_ticket(builder)

    async with create_session_factory(app_engine)() as session:
        await PostgresPseudonymMapStore(session).insert_map(ticket_id, (EMAIL, NAME), NOW)

    assert await builder.scalar("SELECT count(*) FROM pseudonym_map_entries") == 0


async def test_a_concurrent_first_run_waits_and_then_reads_the_map_committed_first(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await new_ticket(builder)

    async with create_session_factory(app_engine)() as first_run:
        await PostgresPseudonymMapStore(first_run).insert_map(ticket_id, (EMAIL, NAME), NOW)
        second_run = asyncio.create_task(insert_and_load(app_engine, ticket_id, (OTHER_NAME,)))
        await wait_until_row_lock_waits(builder, 1, second_run)
        await first_run.commit()
    seen_by_second_run = await second_run

    assert seen_by_second_run == (EMAIL, NAME)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE pseudonym_map_entries SET original_value = 'Lan'",
        "UPDATE pseudonym_map_entries SET pseudonym = '[NAME_2]'",
        "UPDATE pseudonym_map_entries SET pseudonym_type = 'LITERAL'",
        "UPDATE pseudonym_map_entries SET created_at = now()",
        "UPDATE pseudonym_map_entries SET ticket_id = ticket_id",
        "DELETE FROM pseudonym_map_entries",
        "TRUNCATE pseudonym_map_entries",
    ],
)
async def test_supportiq_app_cannot_change_or_remove_a_stored_row(
    app_engine: AsyncEngine, app_engine_raw: AsyncEngine, builder: DatabaseBuilder, statement: str
) -> None:
    ticket_id = await new_ticket(builder)
    await insert_map(app_engine, ticket_id, (NAME,))

    sqlstate = await sqlstate_of_refusal(app_engine_raw, statement)

    assert sqlstate == INSUFFICIENT_PRIVILEGE
    assert await load_entries(app_engine, ticket_id) == (NAME,)
