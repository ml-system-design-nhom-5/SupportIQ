"""Adapter tests of `PostgresTicketLinks` against PostgreSQL 17 (TEST-01).

`suggestions` reads and links ticket rows through these ports: it locks a ticket, makes a
suggestion current, reads the message of a job, and sets the authority flag, which is never
cleared (backend ticket workflow design, Authority).
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts import CustomerId
from app.commerce import OrderId
from app.platform.adapters.database import create_session_factory
from app.suggestions import (
    SuggestionTicketId,
    TicketForSuggestion,
    TicketMessage,
)
from app.tickets import TicketId
from app.tickets.adapters.console_store import (
    PostgresConsoleTicketStore,
    PostgresTicketLinks,
)
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.integration.workflow.workflow_rows import (
    build_new_suggestion,
    insert_suggestion,
    insert_ticket,
    load_authority_flag,
    set_handling_mode,
    set_ticket_status,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

MESSAGE = "I ordered a lamp last week and it has not arrived."
UNKNOWN_TICKET_ID = SuggestionTicketId("TCK-9999")
# PostgreSQL refuses NUL, so no stored row can have this ID.
UNSTORABLE_TICKET_ID = SuggestionTicketId("TCK-\x00")
UNKNOWN_TICKET_IDS = [UNKNOWN_TICKET_ID, UNSTORABLE_TICKET_ID]


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


async def lock_ticket(
    engine: AsyncEngine, ticket_id: SuggestionTicketId
) -> TicketForSuggestion | None:
    async with create_session_factory(engine)() as session:
        return await PostgresTicketLinks(session).lock_ticket(ticket_id)


async def load_ticket_message(
    engine: AsyncEngine, ticket_id: SuggestionTicketId
) -> TicketMessage | None:
    async with create_session_factory(engine)() as session:
        return await PostgresTicketLinks(session).load_ticket_message(ticket_id)


async def set_authority_required(engine: AsyncEngine, ticket_id: SuggestionTicketId) -> None:
    async with create_session_factory(engine)() as session:
        await PostgresTicketLinks(session).set_authority_required(ticket_id)
        await session.commit()


async def test_lock_ticket_of_a_new_ticket_is_open_and_assisted_without_a_suggestion(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)

    locked = await lock_ticket(app_engine, ticket_id)

    assert locked == TicketForSuggestion(
        current_suggestion_id=None, is_open=True, is_assisted=True, status_name="open"
    )


async def test_lock_ticket_tells_a_ticket_that_is_neither_open_nor_assisted(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    await set_ticket_status(owner_engine, ticket_id, "escalated")
    await set_handling_mode(owner_engine, ticket_id, "manual")

    locked = await lock_ticket(app_engine, ticket_id)

    assert locked == TicketForSuggestion(
        current_suggestion_id=None, is_open=False, is_assisted=False, status_name="escalated"
    )


@pytest.mark.parametrize("ticket_id", UNKNOWN_TICKET_IDS)
async def test_lock_ticket_of_an_unknown_ticket_is_none(
    app_engine: AsyncEngine, ticket_id: SuggestionTicketId
) -> None:
    assert await lock_ticket(app_engine, ticket_id) is None


async def test_read_ticket_reads_a_ticket_that_another_transaction_holds_locked(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)

    async with create_session_factory(app_engine)() as holder:
        await PostgresTicketLinks(holder).lock_ticket(ticket_id)
        async with create_session_factory(app_engine)() as reader:
            read = await PostgresTicketLinks(reader).read_ticket(ticket_id)

    assert read == TicketForSuggestion(
        current_suggestion_id=None, is_open=True, is_assisted=True, status_name="open"
    )


async def test_set_current_suggestion_links_the_suggestion_to_the_ticket(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    suggestion = build_new_suggestion(builder, ticket_id, FAKE_CLOCK_START)
    await insert_suggestion(app_engine, suggestion)

    async with create_session_factory(app_engine)() as session:
        await PostgresTicketLinks(session).set_current_suggestion(
            ticket_id, suggestion.suggestion_id
        )
        await session.commit()

    async with create_session_factory(app_engine)() as session:
        ticket = await PostgresConsoleTicketStore(session).load_console_ticket(TicketId(ticket_id))
    assert ticket is not None
    assert ticket.current_suggestion_id == suggestion.suggestion_id


async def test_load_ticket_message_returns_what_a_job_needs(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    _account_id, customer_id = await builder.customer_account()
    order_id = await builder.order_of_one_product(customer_id)
    spec = TicketSpec(message=MESSAGE, created_at=FAKE_CLOCK_START)
    ticket_id = SuggestionTicketId(await builder.ticket(customer_id, order_id, spec))

    message = await load_ticket_message(app_engine, ticket_id)

    assert message == TicketMessage(
        ticket_id=ticket_id,
        message=MESSAGE,
        created_at=FAKE_CLOCK_START,
        customer_id=CustomerId(str(customer_id)),
        order_id=OrderId(order_id),
    )


async def test_load_ticket_message_of_an_imported_ticket_without_an_order_has_no_order(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    _account_id, customer_id = await builder.customer_account()
    imported = TicketSpec(source="import")
    ticket_id = SuggestionTicketId(await builder.ticket(customer_id, None, imported))

    message = await load_ticket_message(app_engine, ticket_id)

    assert message is not None
    assert message.order_id is None


async def test_load_ticket_message_of_an_unknown_ticket_is_none(app_engine: AsyncEngine) -> None:
    assert await load_ticket_message(app_engine, UNKNOWN_TICKET_ID) is None


async def test_set_authority_required_sets_the_flag(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)

    await set_authority_required(app_engine, ticket_id)

    assert await load_authority_flag(builder, ticket_id) is True


async def test_set_authority_required_on_a_flagged_ticket_keeps_the_flag(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder, TicketSpec(is_authority_required=True))

    await set_authority_required(app_engine, ticket_id)

    assert await load_authority_flag(builder, ticket_id) is True
