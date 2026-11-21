"""Adapter tests of `PostgresEscalationStore` against PostgreSQL 17 (TEST-01).

A ticket has one escalation: the unique `ticket_id` of `escalations` refuses a second one. An
escalation is read back with its reasons, its note, and the suggestion that staff saw.
"""

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts import AccountId
from app.platform import DatabaseOperationError
from app.platform.adapters.database import create_session_factory
from app.suggestions import SuggestionId
from app.tickets import (
    Escalation,
    EscalationId,
    EscalationRequest,
    StaffReasonCode,
    TicketId,
)
from app.tickets.adapters.escalation_store import PostgresEscalationStore
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.workflow.workflow_rows import insert_ticket, start_suggestion, ticket_created
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

ESCALATED_AT = FAKE_CLOCK_START + timedelta(minutes=8)
NOTE = "The customer asks to talk to a person."


async def insert_escalation(engine: AsyncEngine, escalation: Escalation) -> None:
    async with create_session_factory(engine)() as session:
        await PostgresEscalationStore(session).insert_escalation(escalation)
        await session.commit()


async def load_escalation(engine: AsyncEngine, ticket_id: TicketId) -> Escalation | None:
    async with create_session_factory(engine)() as session:
        return await PostgresEscalationStore(session).load_escalation(ticket_id)


async def build_escalation(
    builder: DatabaseBuilder, ticket_id: str, suggestion_id: SuggestionId | None
) -> Escalation:
    staff_id = await builder.account(AccountSpec("staff"))
    return Escalation(
        escalation_id=EscalationId(builder.next_uuid()),
        ticket_id=TicketId(ticket_id),
        request=EscalationRequest(
            (StaffReasonCode.CASE_EXCEPTION, StaffReasonCode.OTHER), NOTE, suggestion_id
        ),
        escalated_by=AccountId(str(staff_id)),
        escalated_at=ESCALATED_AT,
    )


async def test_insert_escalation_then_load_escalation_returns_the_escalation(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    escalation = await build_escalation(builder, ticket_id, suggestion_id)

    await insert_escalation(app_engine, escalation)

    assert await load_escalation(app_engine, escalation.ticket_id) == escalation


async def test_an_escalation_without_a_suggestion_is_read_back_without_one(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    escalation = await build_escalation(builder, await insert_ticket(builder), None)

    await insert_escalation(app_engine, escalation)

    assert await load_escalation(app_engine, escalation.ticket_id) == escalation


async def test_load_escalation_before_staff_escalate_is_none(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = TicketId(await insert_ticket(builder))

    assert await load_escalation(app_engine, ticket_id) is None


async def test_insert_escalation_refuses_a_second_escalation_of_the_ticket(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    first = await build_escalation(builder, ticket_id, None)
    await insert_escalation(app_engine, first)
    second = await build_escalation(builder, ticket_id, None)

    with pytest.raises(DatabaseOperationError):
        await insert_escalation(app_engine, second)

    assert await load_escalation(app_engine, first.ticket_id) == first
