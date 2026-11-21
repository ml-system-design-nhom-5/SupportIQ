"""Tests of the rules of reply proposals and escalations: checks, actions, and decisions.

`allowed_actions` is computed by the same rules that the operations check, so the console
never offers a proposal or an escalation that would be refused (backend ticket workflow
design, Ticket state machine and check order).
"""

from dataclasses import replace
from uuid import UUID

import pytest

from app.accounts import SupportRole
from app.suggestions import (
    IntentLabel,
    InvalidTicketStateError,
    Suggestion,
    SuggestionPendingError,
)
from app.tickets import (
    AiDraftReply,
    ConsoleTicket,
    DecisionType,
    EscalationRequest,
    NoAiDraftReply,
    NoteRequiredError,
    PlaceholderInBodyError,
    ProposalId,
    ProposalReply,
    ProposalRequest,
    RejectedAiDraftReply,
    ReplyBasisInvalidError,
    ReplyProposal,
    SentProposal,
    StaffDecision,
    StaffReasonCode,
    TicketAction,
    TicketStatus,
    check_escalation_allowed,
    check_proposal_allowed,
    compute_allowed_actions,
    derive_decision,
    derive_escalation_decision,
    is_proposal_changed,
    parse_sent_proposal,
    validate_escalation_body,
    validate_reply_body,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START
from tests.unit.suggestions.builders import (
    PREDICTED_INTENT,
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    build_ready_suggestion,
    build_suggestion,
)
from tests.unit.tickets.console_fakes import TICKET_ID, build_console_ticket

DRAFT_TEXT = "Hello Lan, your refund is under review."
EDITED_TEXT = "Hello Lan, your refund was approved."
PROPOSAL_ID = ProposalId(UUID("00000000-0000-4000-8000-0000000000ab"))
# The proposal IDs that a request names: opaque strings, compared and never parsed (CON-15).
REQUESTED_PROPOSAL_ID = str(PROPOSAL_ID)
OTHER_PROPOSAL_IDS = [str(UUID(int=8)), "p-1", REQUESTED_PROPOSAL_ID.upper()]
UNCHANGED = AiDraftReply(DRAFT_TEXT, SUGGESTION_ID, frozenset(), (), None)
NOT_OPEN = [TicketStatus.AWAITING_APPROVAL, TicketStatus.ESCALATED, TicketStatus.CLOSED]
HANDOVER_ACTIONS = {TicketAction.SUBMIT_REPLY_PROPOSAL, TicketAction.ESCALATE}


def build_ticket(status: TicketStatus = TicketStatus.OPEN) -> ConsoleTicket:
    return replace(build_console_ticket(status=status), current_suggestion_id=SUGGESTION_ID)


def build_proposal(request: ProposalRequest = UNCHANGED) -> ReplyProposal:
    return ReplyProposal(PROPOSAL_ID, TICKET_ID, request, STAFF_ACCOUNT_ID, FAKE_CLOCK_START)


def test_an_open_ticket_without_a_pending_part_allows_and_offers_a_proposal() -> None:
    ticket = build_ticket()
    suggestion = build_ready_suggestion()

    check_proposal_allowed(ticket, suggestion)

    assert TicketAction.SUBMIT_REPLY_PROPOSAL in compute_allowed_actions(
        ticket, suggestion, SupportRole.STAFF
    )


def test_a_pending_part_refuses_a_proposal_that_the_workspace_does_not_offer() -> None:
    ticket = build_ticket()
    pending = build_suggestion()

    with pytest.raises(SuggestionPendingError):
        check_proposal_allowed(ticket, pending)

    assert TicketAction.SUBMIT_REPLY_PROPOSAL not in compute_allowed_actions(
        ticket, pending, SupportRole.STAFF
    )


def test_a_pending_part_allows_and_offers_an_escalation() -> None:
    ticket = build_ticket()

    check_escalation_allowed(ticket)

    assert TicketAction.ESCALATE in compute_allowed_actions(
        ticket, build_suggestion(), SupportRole.STAFF
    )


@pytest.mark.parametrize("status", NOT_OPEN)
def test_a_ticket_that_is_not_open_refuses_a_proposal_and_offers_none(
    status: TicketStatus,
) -> None:
    ticket = build_ticket(status)

    with pytest.raises(InvalidTicketStateError):
        check_proposal_allowed(ticket, build_ready_suggestion())

    assert compute_allowed_actions(ticket, build_ready_suggestion(), SupportRole.STAFF).isdisjoint(
        HANDOVER_ACTIONS
    )


@pytest.mark.parametrize("status", NOT_OPEN)
def test_a_ticket_that_is_not_open_refuses_an_escalation(status: TicketStatus) -> None:
    with pytest.raises(InvalidTicketStateError) as caught:
        check_escalation_allowed(build_ticket(status))

    assert caught.value.detail == (
        f"The ticket is {status.value}, so this operation is not allowed."
    )


def test_a_manager_is_offered_no_proposal_and_no_escalation() -> None:
    actions = compute_allowed_actions(build_ticket(), build_ready_suggestion(), SupportRole.MANAGER)

    assert actions.isdisjoint(HANDOVER_ACTIONS)


def test_a_reply_on_the_proposal_of_the_ticket_sends_that_proposal() -> None:
    proposal = build_proposal()

    sent = parse_sent_proposal(ProposalReply(EDITED_TEXT, REQUESTED_PROPOSAL_ID), proposal)

    assert (sent.proposal, sent.body) == (proposal, EDITED_TEXT)


@pytest.mark.parametrize(
    "proposal_id", OTHER_PROPOSAL_IDS, ids=["other-uuid", "not-a-uuid", "uppercase"]
)
def test_a_reply_on_another_proposal_is_refused(proposal_id: str) -> None:
    with pytest.raises(ReplyBasisInvalidError):
        parse_sent_proposal(ProposalReply(DRAFT_TEXT, proposal_id), build_proposal())


def test_a_reply_on_a_proposal_of_a_ticket_without_one_is_refused() -> None:
    with pytest.raises(ReplyBasisInvalidError):
        parse_sent_proposal(ProposalReply(DRAFT_TEXT, REQUESTED_PROPOSAL_ID), None)


def test_a_sent_proposal_is_valid_only_while_the_ticket_awaits_approval() -> None:
    sent = SentProposal(build_proposal(), DRAFT_TEXT)

    with pytest.raises(ReplyBasisInvalidError) as caught:
        validate_reply_body(build_ticket(), build_ready_suggestion(), sent)

    assert caught.value.detail == (
        "The basis reply_proposal is not valid while the current draft is draft_ready."
    )


def test_a_sent_proposal_with_a_placeholder_is_refused() -> None:
    sent = SentProposal(build_proposal(), "Hello [NAME_1], your refund was approved.")

    with pytest.raises(PlaceholderInBodyError):
        validate_reply_body(
            build_ticket(TicketStatus.AWAITING_APPROVAL), build_ready_suggestion(), sent
        )


@pytest.mark.parametrize(
    ("proposed", "sent_body", "expected"),
    [
        (UNCHANGED, DRAFT_TEXT, DecisionType.APPROVE),
        (UNCHANGED, EDITED_TEXT, DecisionType.EDIT),
        (replace(UNCHANGED, body=EDITED_TEXT), DRAFT_TEXT, DecisionType.APPROVE),
        (
            RejectedAiDraftReply(EDITED_TEXT, SUGGESTION_ID, (StaffReasonCode.KB_GAP,), None),
            EDITED_TEXT,
            DecisionType.REJECT,
        ),
    ],
    ids=["unchanged-draft", "edited-by-manager", "draft-restored", "rejected-draft"],
)
def test_the_decision_of_a_sent_proposal_comes_from_its_basis_and_the_sent_body(
    proposed: ProposalRequest, sent_body: str, expected: DecisionType
) -> None:
    sent = SentProposal(build_proposal(proposed), sent_body)

    decision = derive_decision(sent, build_ready_suggestion(), DRAFT_TEXT)

    assert decision is not None
    assert (decision.decision_type, decision.suggestion_id, decision.final_intent) == (
        expected,
        SUGGESTION_ID,
        PREDICTED_INTENT,
    )


def test_a_sent_proposal_without_a_draft_records_no_decision() -> None:
    sent = SentProposal(build_proposal(NoAiDraftReply(EDITED_TEXT, None)), EDITED_TEXT)

    assert derive_decision(sent, None, None) is None


@pytest.mark.parametrize(
    ("sent_body", "expected"),
    [(DRAFT_TEXT, False), (f"\n {DRAFT_TEXT}\r\n", False), (EDITED_TEXT, True)],
    ids=["same", "same-after-normalization", "edited"],
)
def test_a_proposal_is_changed_when_the_normalized_bodies_differ(
    sent_body: str, *, expected: bool
) -> None:
    assert is_proposal_changed(SentProposal(build_proposal(), sent_body)) is expected


@pytest.mark.parametrize(
    ("suggestion", "final_intent"),
    [(build_ready_suggestion(), PREDICTED_INTENT), (None, None)],
    ids=["with-suggestion", "manual-mode"],
)
def test_an_escalation_decides_escalate_with_the_intent_of_the_current_suggestion(
    suggestion: Suggestion | None, final_intent: IntentLabel | None
) -> None:
    request = EscalationRequest((StaffReasonCode.CASE_EXCEPTION,), None, None)

    decision = derive_escalation_decision(request, suggestion)

    assert decision == StaffDecision(
        DecisionType.ESCALATE, None, (StaffReasonCode.CASE_EXCEPTION,), None, final_intent
    )


def test_an_escalation_with_other_and_no_note_is_refused() -> None:
    request = EscalationRequest(
        (StaffReasonCode.CASE_EXCEPTION, StaffReasonCode.OTHER), None, SUGGESTION_ID
    )

    with pytest.raises(NoteRequiredError):
        validate_escalation_body(request)
