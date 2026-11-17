"""Tests of `sendReply` with the basis `reply_proposal`, with fakes of every port.

A manager sends the proposal of an `awaiting_approval` ticket, as proposed or edited, and the
decision of the proposal's basis is recorded then, with the staff member who proposed, the
manager who sent, and whether the manager changed the proposed body (contracts v1 design,
Recorded decision; FR-06).
"""

from uuid import UUID

import pytest

from supportiq_backend.accounts import ForbiddenRoleError
from supportiq_backend.audit import AuditEventType
from supportiq_backend.idempotency import IdempotencyKey, StoredResponse
from supportiq_backend.platform import EventName
from supportiq_backend.suggestions import NoDraftStatus
from supportiq_backend.tickets import (
    AiDraftReply,
    DecisionType,
    NoAiDraftReply,
    PlaceholderInBodyError,
    ProposalReply,
    ProposalRequest,
    RecordedDecision,
    RejectedAiDraftReply,
    ReplyBasis,
    ReplyBasisInvalidError,
    ReplyProposal,
    SentReply,
    StaffDecision,
    StaffReasonCode,
    TicketStatus,
    compute_change_ratio,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START
from tests.unit.suggestions.builders import (
    PREDICTED_INTENT,
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    build_draft_ready,
    build_no_draft,
    build_ready_suggestion,
)
from tests.unit.suggestions.fakes import FakeRestorer
from tests.unit.tickets.console_fakes import (
    KEY,
    MANAGER,
    STAFF,
    TICKET_ID,
    ConsoleHarness,
    build_console_harness,
    build_console_ticket,
    build_propose,
    build_send,
    with_suggestion,
)
from tests.unit.tickets.fakes import MANAGER_ACCOUNT_ID

pytestmark = pytest.mark.anyio

DRAFT_TEXT = "Hello [NAME_1], your refund is under review."
RESTORED_DRAFT_TEXT = "Hello Lan Tran, your refund is under review."
RESTORER = FakeRestorer({"[NAME_1]": "Lan Tran"})
STAFF_EDIT = "Hello Lan Tran, your refund is under review. We will write again on Friday."
MANAGER_EDIT = "Hello Lan Tran, your refund was approved today."
OWN_TEXT = "A manager will confirm your refund."
SEND_KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000124"))
OTHER_PROPOSAL_ID = "00000000-0000-4000-8000-0000000000f1"
UNCHANGED = AiDraftReply(RESTORED_DRAFT_TEXT, SUGGESTION_ID, frozenset(), (), None)
EDITED = AiDraftReply(
    STAFF_EDIT, SUGGESTION_ID, frozenset(), (StaffReasonCode.TONE_OR_CLARITY,), None
)
REJECTED = RejectedAiDraftReply(OWN_TEXT, SUGGESTION_ID, (StaffReasonCode.WRONG_INTENT,), None)


async def proposed(proposal: ProposalRequest) -> tuple[ConsoleHarness, ReplyProposal]:
    """Let staff propose on a ticket with a ready draft that requires authority."""
    harness = with_suggestion(
        build_console_harness(build_console_ticket(is_authority_required=True), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )
    await build_propose(harness).execute(STAFF, TICKET_ID, proposal, KEY)
    return harness, harness.proposals.proposals[TICKET_ID]


async def send(harness: ConsoleHarness, proposal: ReplyProposal, body: str) -> StoredResponse:
    reply = ProposalReply(body, str(proposal.proposal_id))
    return await build_send(harness).execute(MANAGER, TICKET_ID, reply, SEND_KEY)


def recorded_decision(harness: ConsoleHarness) -> RecordedDecision:
    (decision,) = harness.replies.decisions
    return decision


async def test_a_manager_sends_an_unchanged_proposal_of_the_draft_as_approve() -> None:
    harness, proposal = await proposed(UNCHANGED)

    await send(harness, proposal, RESTORED_DRAFT_TEXT)

    recorded = recorded_decision(harness)
    assert recorded.decision == StaffDecision(
        DecisionType.APPROVE, SUGGESTION_ID, (), 0.0, PREDICTED_INTENT
    )
    assert (recorded.decided_by, recorded.proposed_by, recorded.is_proposal_changed) == (
        MANAGER_ACCOUNT_ID,
        STAFF_ACCOUNT_ID,
        False,
    )
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.CLOSED


async def test_a_manager_who_edits_the_proposal_of_the_draft_records_an_edit() -> None:
    harness, proposal = await proposed(UNCHANGED)

    await send(harness, proposal, MANAGER_EDIT)

    recorded = recorded_decision(harness)
    assert recorded.decision.decision_type is DecisionType.EDIT
    assert recorded.decision.change_ratio == compute_change_ratio(RESTORED_DRAFT_TEXT, MANAGER_EDIT)
    assert recorded.is_proposal_changed is True


async def test_an_edit_of_staff_sent_as_proposed_is_an_edit_with_no_proposal_change() -> None:
    harness, proposal = await proposed(EDITED)

    await send(harness, proposal, STAFF_EDIT)

    recorded = recorded_decision(harness)
    assert recorded.decision == StaffDecision(
        DecisionType.EDIT,
        SUGGESTION_ID,
        (StaffReasonCode.TONE_OR_CLARITY,),
        compute_change_ratio(RESTORED_DRAFT_TEXT, STAFF_EDIT),
        PREDICTED_INTENT,
    )
    assert recorded.is_proposal_changed is False


async def test_a_manager_who_sends_the_draft_instead_of_an_edit_approves_it() -> None:
    harness, proposal = await proposed(EDITED)

    await send(harness, proposal, RESTORED_DRAFT_TEXT)

    recorded = recorded_decision(harness)
    assert recorded.decision.decision_type is DecisionType.APPROVE
    assert recorded.is_proposal_changed is True


async def test_the_proposed_body_is_compared_after_line_endings_and_outer_spaces() -> None:
    harness, proposal = await proposed(EDITED)

    await send(harness, proposal, f"  {STAFF_EDIT}\r\n")

    assert recorded_decision(harness).is_proposal_changed is False


async def test_a_proposal_that_rejects_the_draft_records_reject() -> None:
    harness, proposal = await proposed(REJECTED)

    await send(harness, proposal, OWN_TEXT)

    recorded = recorded_decision(harness)
    assert recorded.decision == StaffDecision(
        DecisionType.REJECT, SUGGESTION_ID, (StaffReasonCode.WRONG_INTENT,), None, PREDICTED_INTENT
    )
    assert recorded.is_proposal_changed is False


async def test_a_proposal_without_a_draft_records_no_decision() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket()),
        build_ready_suggestion(build_no_draft(NoDraftStatus.ABSTAINED)),
    )
    await build_propose(harness).execute(
        STAFF, TICKET_ID, NoAiDraftReply(OWN_TEXT, SUGGESTION_ID), KEY
    )

    await send(harness, harness.proposals.proposals[TICKET_ID], OWN_TEXT)

    assert harness.replies.decisions == []
    assert harness.events.of(EventName.DECISION_RECORDED) == ()
    assert harness.replies.replies[TICKET_ID].suggestion_id == SUGGESTION_ID


async def test_the_reply_names_the_proposal_and_holds_what_the_manager_sent() -> None:
    harness, proposal = await proposed(EDITED)

    await send(harness, proposal, MANAGER_EDIT)

    reply = harness.replies.replies[TICKET_ID]
    assert reply == SentReply(
        reply_id=reply.reply_id,
        ticket_id=TICKET_ID,
        basis=ReplyBasis.REPLY_PROPOSAL,
        body=MANAGER_EDIT,
        suggestion_id=SUGGESTION_ID,
        proposal_id=proposal.proposal_id,
        acknowledged_warning_ids=(),
        staff_reason_codes=(),
        note=None,
        sent_by=MANAGER_ACCOUNT_ID,
        sent_at=FAKE_CLOCK_START,
    )


async def test_the_audit_entries_name_the_proposer_and_the_decision() -> None:
    harness, proposal = await proposed(UNCHANGED)

    await send(harness, proposal, RESTORED_DRAFT_TEXT)

    submitted, sent, decided = harness.audit.entries
    assert submitted.event_type is AuditEventType.REPLY_PROPOSAL_SUBMITTED
    assert (sent.event_type, sent.actor_account_id) == (
        AuditEventType.REPLY_SENT,
        MANAGER_ACCOUNT_ID,
    )
    assert sent.data == {
        "reply_id": str(harness.replies.replies[TICKET_ID].reply_id),
        "basis": "reply_proposal",
        "proposed_by_account_id": STAFF_ACCOUNT_ID,
    }
    assert (decided.event_type, decided.actor_account_id) == (
        AuditEventType.DECISION_RECORDED,
        MANAGER_ACCOUNT_ID,
    )
    assert decided.data == {
        "decision_type": "approve",
        "staff_reason_codes": "",
        "suggestion_id": SUGGESTION_ID,
        "change_ratio_thousandths": 0,
    }


async def test_the_events_of_a_proposal_send_name_the_decision() -> None:
    harness, proposal = await proposed(UNCHANGED)

    await send(harness, proposal, MANAGER_EDIT)

    (sent,) = harness.events.of(EventName.REPLY_SENT)
    (decided,) = harness.events.of(EventName.DECISION_RECORDED)
    assert sent.attributes == {"ticket_id": TICKET_ID}
    assert decided.attributes == {
        "ticket_id": TICKET_ID,
        "suggestion_id": SUGGESTION_ID,
        "decision_type": "edit",
    }


async def test_another_proposal_id_is_refused_and_nothing_is_sent() -> None:
    harness, _proposal = await proposed(UNCHANGED)
    reply = ProposalReply(RESTORED_DRAFT_TEXT, OTHER_PROPOSAL_ID)

    with pytest.raises(ReplyBasisInvalidError) as caught:
        await build_send(harness).execute(MANAGER, TICKET_ID, reply, SEND_KEY)

    assert caught.value.detail == (
        "The basis reply_proposal is not valid with a proposal_id that is not the proposal of"
        " the ticket."
    )
    assert harness.replies.replies == {}
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.AWAITING_APPROVAL


async def test_a_proposal_reply_on_an_open_ticket_is_refused() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )
    reply = ProposalReply(RESTORED_DRAFT_TEXT, OTHER_PROPOSAL_ID)

    with pytest.raises(ReplyBasisInvalidError):
        await build_send(harness).execute(MANAGER, TICKET_ID, reply, SEND_KEY)

    assert harness.replies.replies == {}


async def test_a_manager_sends_an_awaiting_ticket_only_with_its_proposal() -> None:
    harness, _proposal = await proposed(UNCHANGED)

    with pytest.raises(ReplyBasisInvalidError) as caught:
        await build_send(harness).execute(MANAGER, TICKET_ID, UNCHANGED, SEND_KEY)

    assert caught.value.detail == (
        "The basis ai_draft is not valid while the current draft is draft_ready."
    )


async def test_a_proposal_reply_with_a_placeholder_is_refused() -> None:
    harness, proposal = await proposed(UNCHANGED)

    with pytest.raises(PlaceholderInBodyError):
        await send(harness, proposal, DRAFT_TEXT)

    assert harness.replies.replies == {}
    assert harness.replies.decisions == []


async def test_staff_may_not_send_the_proposal_that_they_submitted() -> None:
    harness, proposal = await proposed(UNCHANGED)
    reply = ProposalReply(RESTORED_DRAFT_TEXT, str(proposal.proposal_id))

    with pytest.raises(ForbiddenRoleError):
        await build_send(harness).execute(STAFF, TICKET_ID, reply, SEND_KEY)

    assert harness.replies.replies == {}


async def test_a_repeated_proposal_reply_sends_nothing_more() -> None:
    harness, proposal = await proposed(UNCHANGED)
    first = await send(harness, proposal, RESTORED_DRAFT_TEXT)

    repeated = await send(harness, proposal, RESTORED_DRAFT_TEXT)

    assert repeated == first
    assert len(harness.replies.decisions) == 1
    assert len(harness.events.of(EventName.REPLY_SENT)) == 1
