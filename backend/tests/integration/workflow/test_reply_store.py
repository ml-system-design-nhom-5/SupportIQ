"""Adapter tests of `PostgresReplyStore` against PostgreSQL 17 (TEST-01).

A ticket has one reply: the unique `ticket_id` of `replies` refuses a second one (ERR-16). A
staff decision is inserted once and holds no text (ADR-0006); an escalation's decision may name
no suggestion.
"""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts import AccountId
from app.platform import DatabaseOperationError
from app.platform.adapters.database import create_session_factory
from app.suggestions import IntentLabel
from app.tickets import (
    DecisionId,
    DecisionType,
    RecordedDecision,
    ReplyBasis,
    ReplyId,
    SentReply,
    StaffDecision,
    StaffReasonCode,
    TicketId,
)
from app.tickets.adapters.reply_store import PostgresReplyStore
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.workflow.workflow_rows import insert_ticket, start_suggestion, ticket_created
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

SENT_AT = FAKE_CLOCK_START + timedelta(minutes=30)
CHANGE_RATIO = 0.25
REPLY_BODY = "Your parcel left the warehouse today and should arrive on Friday."
DECISION_COLUMNS = """
    SELECT jsonb_build_object(
        'ticket_id', ticket_id, 'suggestion_id', suggestion_id, 'decision_type', decision_type,
        'staff_reason_codes', staff_reason_codes, 'change_ratio', change_ratio,
        'final_intent', final_intent, 'decided_by', decided_by_account_id,
        'proposed_by', proposed_by_account_id, 'is_proposal_changed', is_proposal_changed
    )
    FROM staff_decisions
"""


async def insert_reply(engine: AsyncEngine, reply: SentReply) -> None:
    async with create_session_factory(engine)() as session:
        await PostgresReplyStore(session).insert_reply(reply)
        await session.commit()


async def load_reply(engine: AsyncEngine, ticket_id: TicketId) -> SentReply | None:
    async with create_session_factory(engine)() as session:
        return await PostgresReplyStore(session).load_reply(ticket_id)


async def build_edited_reply(engine: AsyncEngine, builder: DatabaseBuilder) -> SentReply:
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(engine, builder, ticket_created(ticket_id))
    staff_id = await builder.account(AccountSpec("staff"))
    return SentReply(
        reply_id=ReplyId(builder.next_uuid()),
        ticket_id=TicketId(ticket_id),
        basis=ReplyBasis.AI_DRAFT,
        body=REPLY_BODY,
        suggestion_id=suggestion_id,
        proposal_id=None,
        acknowledged_warning_ids=("w-review-overdue", "w-conflicting-sources"),
        staff_reason_codes=(StaffReasonCode.TONE_OR_CLARITY, StaffReasonCode.OTHER),
        note="Shortened the second paragraph.",
        sent_by=AccountId(str(staff_id)),
        sent_at=SENT_AT,
    )


async def test_insert_reply_then_load_reply_returns_the_reply(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    reply = await build_edited_reply(app_engine, builder)

    await insert_reply(app_engine, reply)

    assert await load_reply(app_engine, reply.ticket_id) == reply


async def test_load_reply_before_the_reply_is_sent_is_none(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = TicketId(await insert_ticket(builder))

    assert await load_reply(app_engine, ticket_id) is None


async def test_insert_reply_refuses_a_second_reply_of_the_ticket(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    first = await build_edited_reply(app_engine, builder)
    await insert_reply(app_engine, first)
    second = SentReply(
        reply_id=ReplyId(builder.next_uuid()),
        ticket_id=first.ticket_id,
        basis=ReplyBasis.NO_AI_DRAFT,
        body="A second answer.",
        suggestion_id=None,
        proposal_id=None,
        acknowledged_warning_ids=(),
        staff_reason_codes=(),
        note=None,
        sent_by=first.sent_by,
        sent_at=SENT_AT,
    )

    with pytest.raises(DatabaseOperationError):
        await insert_reply(app_engine, second)

    assert await load_reply(app_engine, first.ticket_id) == first


async def test_insert_decision_stores_every_field_of_the_decision(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    manager_id = await builder.account(AccountSpec("manager"))
    staff_id = await builder.account(AccountSpec("staff"))
    decision = RecordedDecision(
        decision_id=DecisionId(builder.next_uuid()),
        ticket_id=TicketId(ticket_id),
        decision=StaffDecision(
            decision_type=DecisionType.EDIT,
            suggestion_id=suggestion_id,
            staff_reason_codes=(StaffReasonCode.MISSING_CASE_INFO,),
            change_ratio=CHANGE_RATIO,
            final_intent=IntentLabel.TRACK_ORDER,
        ),
        decided_by=AccountId(str(manager_id)),
        proposed_by=AccountId(str(staff_id)),
        is_proposal_changed=True,
        decided_at=SENT_AT,
    )

    async with create_session_factory(app_engine)() as session:
        await PostgresReplyStore(session).insert_decision(decision)
        await session.commit()

    assert await builder.scalar(DECISION_COLUMNS) == {
        "ticket_id": ticket_id,
        "suggestion_id": str(UUID(suggestion_id)),
        "decision_type": "edit",
        "staff_reason_codes": ["missing_case_info"],
        "change_ratio": CHANGE_RATIO,
        "final_intent": "track_order",
        "decided_by": str(manager_id),
        "proposed_by": str(staff_id),
        "is_proposal_changed": True,
    }


async def test_insert_decision_stores_an_escalation_that_names_no_suggestion(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    staff_id = await builder.account(AccountSpec("staff"))
    decision = RecordedDecision(
        decision_id=DecisionId(builder.next_uuid()),
        ticket_id=TicketId(ticket_id),
        decision=StaffDecision(
            decision_type=DecisionType.ESCALATE,
            suggestion_id=None,
            staff_reason_codes=(StaffReasonCode.CASE_EXCEPTION, StaffReasonCode.OTHER),
            change_ratio=None,
            final_intent=None,
        ),
        decided_by=AccountId(str(staff_id)),
        proposed_by=None,
        is_proposal_changed=None,
        decided_at=SENT_AT,
    )

    async with create_session_factory(app_engine)() as session:
        await PostgresReplyStore(session).insert_decision(decision)
        await session.commit()

    assert await builder.scalar(DECISION_COLUMNS) == {
        "ticket_id": ticket_id,
        "suggestion_id": None,
        "decision_type": "escalate",
        "staff_reason_codes": ["case_exception", "other"],
        "change_ratio": None,
        "final_intent": None,
        "decided_by": str(staff_id),
        "proposed_by": None,
        "is_proposal_changed": None,
    }
