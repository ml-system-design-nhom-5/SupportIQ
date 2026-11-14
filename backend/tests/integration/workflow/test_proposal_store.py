"""Adapter tests of `PostgresReplyProposalStore` against PostgreSQL 17 (TEST-01).

A proposal is inserted once and read back with its basis, so a proposal on a draft keeps its
suggestion, acknowledged warnings, staff reason codes, and note (contracts v1 design).
"""

from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.accounts import AccountId
from supportiq_backend.platform.adapters.database import create_session_factory
from supportiq_backend.suggestions import SuggestionId
from supportiq_backend.tickets import (
    AiDraftReply,
    NoAiDraftReply,
    ProposalId,
    ProposalRequest,
    RejectedAiDraftReply,
    ReplyProposal,
    StaffReasonCode,
    TicketId,
)
from supportiq_backend.tickets.adapters.proposal_store import PostgresReplyProposalStore
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.workflow.workflow_rows import insert_ticket, start_suggestion, ticket_created
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

CREATED_AT = FAKE_CLOCK_START + timedelta(minutes=12)
BODY = "Your refund request is under review. A manager will confirm it today."
NOTE = "The customer asked twice."
type RequestOf = Callable[[SuggestionId], ProposalRequest]
PROPOSAL_COLUMNS = """
    SELECT jsonb_build_object(
        'basis', basis, 'suggestion_id', suggestion_id,
        'acknowledged_warning_ids', acknowledged_warning_ids,
        'staff_reason_codes', staff_reason_codes, 'body', body, 'note', note
    )
    FROM reply_proposals
"""


async def insert_proposal(engine: AsyncEngine, proposal: ReplyProposal) -> None:
    async with create_session_factory(engine)() as session:
        await PostgresReplyProposalStore(session).insert_proposal(proposal)
        await session.commit()


async def load_proposal(engine: AsyncEngine, ticket_id: TicketId) -> ReplyProposal | None:
    async with create_session_factory(engine)() as session:
        return await PostgresReplyProposalStore(session).load_proposal(ticket_id)


def on_the_draft(suggestion_id: SuggestionId) -> ProposalRequest:
    return AiDraftReply(
        body=BODY,
        suggestion_id=suggestion_id,
        acknowledged_warning_ids=frozenset({"w-review-overdue", "w-conflicting-sources"}),
        staff_reason_codes=(StaffReasonCode.TONE_OR_CLARITY, StaffReasonCode.OTHER),
        note=NOTE,
    )


def rejecting_the_draft(suggestion_id: SuggestionId) -> ProposalRequest:
    return RejectedAiDraftReply(BODY, suggestion_id, (StaffReasonCode.WRONG_SOURCE,), None)


def without_a_draft(suggestion_id: SuggestionId) -> ProposalRequest:
    return NoAiDraftReply(BODY, suggestion_id)


def without_a_suggestion(suggestion_id: SuggestionId) -> ProposalRequest:
    del suggestion_id
    return NoAiDraftReply(BODY, None)


async def build_proposal(
    engine: AsyncEngine, builder: DatabaseBuilder, request_of: RequestOf
) -> ReplyProposal:
    """Build a proposal of a new ticket that has a suggestion, from the request of its basis."""
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(engine, builder, ticket_created(ticket_id))
    staff_id = await builder.account(AccountSpec("staff"))
    return ReplyProposal(
        proposal_id=ProposalId(builder.next_uuid()),
        ticket_id=TicketId(ticket_id),
        request=request_of(suggestion_id),
        proposed_by=AccountId(str(staff_id)),
        created_at=CREATED_AT,
    )


@pytest.mark.parametrize(
    "request_of",
    [on_the_draft, rejecting_the_draft, without_a_draft, without_a_suggestion],
    ids=["ai-draft", "rejected-ai-draft", "no-ai-draft", "no-suggestion"],
)
async def test_insert_proposal_then_load_proposal_returns_the_proposal_of_each_basis(
    app_engine: AsyncEngine, builder: DatabaseBuilder, request_of: RequestOf
) -> None:
    proposal = await build_proposal(app_engine, builder, request_of)

    await insert_proposal(app_engine, proposal)

    assert await load_proposal(app_engine, proposal.ticket_id) == proposal


async def test_insert_proposal_stores_the_fields_of_its_basis(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    proposal = await build_proposal(app_engine, builder, on_the_draft)

    await insert_proposal(app_engine, proposal)

    assert await builder.scalar(PROPOSAL_COLUMNS) == {
        "basis": "ai_draft",
        "suggestion_id": proposal.request.suggestion_id,
        "acknowledged_warning_ids": ["w-conflicting-sources", "w-review-overdue"],
        "staff_reason_codes": ["tone_or_clarity", "other"],
        "body": BODY,
        "note": NOTE,
    }


async def test_a_proposal_without_a_draft_is_stored_without_codes_or_note(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    proposal = await build_proposal(app_engine, builder, without_a_suggestion)

    await insert_proposal(app_engine, proposal)

    assert await builder.scalar(PROPOSAL_COLUMNS) == {
        "basis": "no_ai_draft",
        "suggestion_id": None,
        "acknowledged_warning_ids": [],
        "staff_reason_codes": [],
        "body": BODY,
        "note": None,
    }


async def test_load_proposal_before_staff_submit_one_is_none(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = TicketId(await insert_ticket(builder))

    assert await load_proposal(app_engine, ticket_id) is None
