"""Adapter tests of `PostgresConsoleTicketStore` against PostgreSQL 17 (TEST-01).

Each console queue lists one status: `open`, `awaiting_approval`, and `escalated` oldest first
by `created_at`, `closed` newest first by `closed_at`, then by ticket ID by code point, and a
page continues after the position of the last ticket of the previous one (contract
`listConsoleTickets`). Every action locks the ticket row first (backend ticket workflow design,
Ticket state machine and check order).
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce import OrderId
from supportiq_backend.platform.adapters.database import create_session_factory
from supportiq_backend.tickets import (
    ConsoleTicket,
    ConsoleTicketPosition,
    HandlingMode,
    TicketId,
    TicketStatus,
)
from supportiq_backend.tickets.adapters.console_store import PostgresConsoleTicketStore
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.integration.workflow.workflow_rows import set_ticket_status, wait_until_row_lock_waits
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

FIRST = FAKE_CLOCK_START
SECOND = FAKE_CLOCK_START + timedelta(minutes=1)
THIRD = FAKE_CLOCK_START + timedelta(minutes=2)
FIRST_VIEW_AT = FAKE_CLOCK_START + timedelta(minutes=10)
LATER_VIEW_AT = FAKE_CLOCK_START + timedelta(minutes=20)
PAGE_LIMIT = 20
MESSAGE = "Where is my parcel? It was due on Monday."
UNKNOWN_TICKET_IDS = [TicketId("TCK-9999"), TicketId("TCK-\x00")]
QUEUES_BY_CREATION = [TicketStatus.OPEN, TicketStatus.AWAITING_APPROVAL, TicketStatus.ESCALATED]
HANDLING_STARTED_AT = "SELECT handling_started_at FROM tickets"


@dataclass(frozen=True, slots=True)
class CustomerOrder:
    """A customer and one of its orders, which the tickets of a test are about.

    Attributes:
        customer_id: The customer.
        order_id: The order.
    """

    customer_id: UUID
    order_id: str


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


@pytest.fixture
async def customer_order(builder: DatabaseBuilder) -> CustomerOrder:
    _account_id, customer_id = await builder.customer_account()
    return CustomerOrder(customer_id, await builder.order_of_one_product(customer_id))


async def insert_ticket_at(
    builder: DatabaseBuilder, customer_order: CustomerOrder, created_at: datetime
) -> TicketId:
    spec = TicketSpec(message=MESSAGE, created_at=created_at)
    return TicketId(await builder.ticket(customer_order.customer_id, customer_order.order_id, spec))


async def insert_closed_ticket(
    owner_engine: AsyncEngine,
    builder: DatabaseBuilder,
    customer_order: CustomerOrder,
    closed_at: datetime,
) -> TicketId:
    ticket_id = await insert_ticket_at(builder, customer_order, FIRST)
    await set_ticket_status(owner_engine, ticket_id, TicketStatus.CLOSED.value, closed_at=closed_at)
    return ticket_id


async def list_queue(
    engine: AsyncEngine,
    status: TicketStatus,
    *,
    after: ConsoleTicketPosition | None = None,
    limit: int = PAGE_LIMIT,
) -> tuple[TicketId, ...]:
    async with create_session_factory(engine)() as session:
        tickets = await PostgresConsoleTicketStore(session).load_console_tickets(
            status, after=after, limit=limit
        )
    return tuple(ticket.ticket_id for ticket in tickets)


async def load_ticket(engine: AsyncEngine, ticket_id: TicketId) -> ConsoleTicket | None:
    async with create_session_factory(engine)() as session:
        return await PostgresConsoleTicketStore(session).load_console_ticket(ticket_id)


async def lock_and_commit(engine: AsyncEngine, ticket_id: TicketId) -> ConsoleTicket | None:
    async with create_session_factory(engine)() as session:
        ticket = await PostgresConsoleTicketStore(session).lock_console_ticket(ticket_id)
        await session.commit()
    return ticket


async def start_handling(engine: AsyncEngine, ticket_id: TicketId, started_at: datetime) -> None:
    async with create_session_factory(engine)() as session:
        await PostgresConsoleTicketStore(session).start_handling(ticket_id, started_at)
        await session.commit()


async def test_load_console_ticket_returns_the_ticket_with_its_message(
    app_engine: AsyncEngine, builder: DatabaseBuilder, customer_order: CustomerOrder
) -> None:
    ticket_id = await insert_ticket_at(builder, customer_order, FIRST)

    ticket = await load_ticket(app_engine, ticket_id)

    assert ticket == ConsoleTicket(
        ticket_id=ticket_id,
        status=TicketStatus.OPEN,
        handling_mode=HandlingMode.ASSISTED,
        is_authority_required=False,
        created_at=FIRST,
        handling_started_at=None,
        closed_at=None,
        customer_id=CustomerId(str(customer_order.customer_id)),
        order_id=OrderId(customer_order.order_id),
        current_suggestion_id=None,
        message=MESSAGE,
    )


@pytest.mark.parametrize("ticket_id", UNKNOWN_TICKET_IDS)
async def test_load_console_ticket_of_an_unknown_ticket_is_none(
    app_engine: AsyncEngine, ticket_id: TicketId
) -> None:
    assert await load_ticket(app_engine, ticket_id) is None


@pytest.mark.parametrize("ticket_id", UNKNOWN_TICKET_IDS)
async def test_lock_console_ticket_of_an_unknown_ticket_is_none(
    app_engine: AsyncEngine, ticket_id: TicketId
) -> None:
    assert await lock_and_commit(app_engine, ticket_id) is None


async def test_lock_console_ticket_holds_the_row_until_the_transaction_ends(
    app_engine: AsyncEngine, builder: DatabaseBuilder, customer_order: CustomerOrder
) -> None:
    ticket_id = await insert_ticket_at(builder, customer_order, FIRST)

    async with create_session_factory(app_engine)() as first_action:
        await PostgresConsoleTicketStore(first_action).lock_console_ticket(ticket_id)
        second_action = asyncio.create_task(lock_and_commit(app_engine, ticket_id))
        await wait_until_row_lock_waits(builder, 1, second_action)
        await first_action.commit()
    locked_by_second_action = await second_action

    assert locked_by_second_action is not None
    assert locked_by_second_action.ticket_id == ticket_id


@pytest.mark.parametrize("status", QUEUES_BY_CREATION)
async def test_load_console_tickets_lists_one_status_oldest_first(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    builder: DatabaseBuilder,
    customer_order: CustomerOrder,
    status: TicketStatus,
) -> None:
    newer = await insert_ticket_at(builder, customer_order, SECOND)
    older = await insert_ticket_at(builder, customer_order, FIRST)
    await insert_closed_ticket(owner_engine, builder, customer_order, THIRD)
    await set_ticket_status(owner_engine, newer, status.value)
    await set_ticket_status(owner_engine, older, status.value)

    listed = await list_queue(app_engine, status)

    assert listed == (older, newer)


async def test_load_console_tickets_lists_closed_tickets_newest_closed_first(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    builder: DatabaseBuilder,
    customer_order: CustomerOrder,
) -> None:
    closed_second = await insert_closed_ticket(owner_engine, builder, customer_order, SECOND)
    closed_third = await insert_closed_ticket(owner_engine, builder, customer_order, THIRD)
    closed_first = await insert_closed_ticket(owner_engine, builder, customer_order, FIRST)
    await insert_ticket_at(builder, customer_order, FIRST)

    listed = await list_queue(app_engine, TicketStatus.CLOSED)

    assert listed == (closed_third, closed_second, closed_first)


async def test_load_console_tickets_orders_tickets_of_one_moment_by_ticket_id(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    builder: DatabaseBuilder,
    customer_order: CustomerOrder,
) -> None:
    lower = await insert_closed_ticket(owner_engine, builder, customer_order, SECOND)
    higher = await insert_closed_ticket(owner_engine, builder, customer_order, SECOND)

    listed = await list_queue(app_engine, TicketStatus.CLOSED)

    assert listed == (lower, higher)


async def test_load_console_tickets_returns_at_most_the_limit(
    app_engine: AsyncEngine, builder: DatabaseBuilder, customer_order: CustomerOrder
) -> None:
    oldest = await insert_ticket_at(builder, customer_order, FIRST)
    await insert_ticket_at(builder, customer_order, SECOND)

    listed = await list_queue(app_engine, TicketStatus.OPEN, limit=1)

    assert listed == (oldest,)


async def test_load_console_tickets_continues_after_the_position(
    app_engine: AsyncEngine, builder: DatabaseBuilder, customer_order: CustomerOrder
) -> None:
    first = await insert_ticket_at(builder, customer_order, FIRST)
    same_moment = await insert_ticket_at(builder, customer_order, FIRST)
    later = await insert_ticket_at(builder, customer_order, SECOND)
    position = ConsoleTicketPosition(TicketStatus.OPEN, FIRST, first)

    listed = await list_queue(app_engine, TicketStatus.OPEN, after=position)

    assert listed == (same_moment, later)


async def test_load_console_tickets_continues_after_the_position_in_the_closed_queue(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    builder: DatabaseBuilder,
    customer_order: CustomerOrder,
) -> None:
    last_of_page = await insert_closed_ticket(owner_engine, builder, customer_order, SECOND)
    same_moment = await insert_closed_ticket(owner_engine, builder, customer_order, SECOND)
    earlier = await insert_closed_ticket(owner_engine, builder, customer_order, FIRST)
    await insert_closed_ticket(owner_engine, builder, customer_order, THIRD)
    position = ConsoleTicketPosition(TicketStatus.CLOSED, SECOND, last_of_page)

    listed = await list_queue(app_engine, TicketStatus.CLOSED, after=position)

    assert listed == (same_moment, earlier)


async def test_start_handling_sets_the_time_of_the_first_view(
    app_engine: AsyncEngine, builder: DatabaseBuilder, customer_order: CustomerOrder
) -> None:
    ticket_id = await insert_ticket_at(builder, customer_order, FIRST)

    await start_handling(app_engine, ticket_id, FIRST_VIEW_AT)

    assert await builder.scalar(HANDLING_STARTED_AT) == FIRST_VIEW_AT


async def test_start_handling_keeps_the_time_of_the_first_view(
    app_engine: AsyncEngine, builder: DatabaseBuilder, customer_order: CustomerOrder
) -> None:
    ticket_id = await insert_ticket_at(builder, customer_order, FIRST)
    await start_handling(app_engine, ticket_id, FIRST_VIEW_AT)

    await start_handling(app_engine, ticket_id, LATER_VIEW_AT)

    assert await builder.scalar(HANDLING_STARTED_AT) == FIRST_VIEW_AT


async def test_close_ticket_sets_the_ticket_closed_at_the_time_of_the_reply(
    app_engine: AsyncEngine, builder: DatabaseBuilder, customer_order: CustomerOrder
) -> None:
    ticket_id = await insert_ticket_at(builder, customer_order, FIRST)

    async with create_session_factory(app_engine)() as session:
        await PostgresConsoleTicketStore(session).close_ticket(ticket_id, THIRD)
        await session.commit()

    closed = await load_ticket(app_engine, ticket_id)
    assert closed is not None
    assert (closed.status, closed.closed_at) == (TicketStatus.CLOSED, THIRD)
