"""The staff decision that a reply or an escalation records (contracts v1 design, ADR-0006).

A decision holds no text: it names the suggestion, the staff reason codes, and how much the
sent body differs from the draft.
"""

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from enum import StrEnum
from typing import NewType, assert_never
from uuid import UUID

from app.accounts import AccountId
from app.suggestions import IntentLabel, Suggestion, SuggestionId
from app.tickets.domain.escalations import EscalationRequest
from app.tickets.domain.proposals import ResolvedReply, SentProposal
from app.tickets.domain.reply_requests import (
    AiDraftReply,
    NoAiDraftReply,
    ProposalRequest,
    RejectedAiDraftReply,
    StaffReasonCode,
)
from app.tickets.domain.tickets import TicketId

DecisionId = NewType("DecisionId", UUID)

# `change_ratio` has three decimals: 0 for an unchanged draft, up to 1 for a rewrite.
CHANGE_RATIO_DECIMALS = 3


class DecisionType(StrEnum):
    """What staff or a manager did with a suggestion (ADR-0006)."""

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class StaffDecision:
    """The decision that a reply or an escalation records; it holds no text (ADR-0006).

    Attributes:
        decision_type: Approve, edit, reject, or escalate.
        suggestion_id: The suggestion of the draft; absent for an escalation that names none.
        staff_reason_codes: The staff reason codes.
        change_ratio: How much the body differs from the draft, in [0, 1]; only for a reply
            based on a draft.
        final_intent: The intent of the current suggestion, staff-chosen after an override.
    """

    decision_type: DecisionType
    suggestion_id: SuggestionId | None
    staff_reason_codes: tuple[StaffReasonCode, ...]
    change_ratio: float | None
    final_intent: IntentLabel | None


@dataclass(frozen=True, slots=True)
class RecordedDecision:
    """A staff decision as `staff_decisions` stores it, once (ADR-0006).

    Attributes:
        decision_id: The identifier.
        ticket_id: The ticket.
        decision: What was decided.
        decided_by: The account that sent the reply or escalated the ticket.
        proposed_by: The staff member who proposed it, for a reply from a proposal.
        is_proposal_changed: Whether the manager changed the proposed body.
        decided_at: When the reply was sent or the ticket escalated.
    """

    decision_id: DecisionId
    ticket_id: TicketId
    decision: StaffDecision
    decided_by: AccountId
    proposed_by: AccountId | None
    is_proposal_changed: bool | None
    decided_at: datetime


def derive_decision(
    reply: ResolvedReply, suggestion: Suggestion | None, draft_text: str | None
) -> StaffDecision | None:
    """Derive the decision that a reply records (contracts v1 design, Recorded decision).

    A reply from a proposal records the decision of the proposal's basis, with the body that
    the manager sends.

    Args:
        reply: The body of the request, valid already, with its proposal resolved.
        suggestion: The current suggestion, when there is one.
        draft_text: The canonical text of its ready draft, pseudonyms restored.

    Returns:
        `approve` or `edit` for a reply on a draft, `reject` for a rejected draft, and None
        for a reply without a draft.
    """
    match reply:
        case SentProposal():
            return _derive_from_basis(reply.proposal.request, reply.body, suggestion, draft_text)
        case AiDraftReply() | RejectedAiDraftReply() | NoAiDraftReply():
            return _derive_from_basis(reply, reply.body, suggestion, draft_text)
        case _:
            assert_never(reply)


def derive_escalation_decision(
    request: EscalationRequest, suggestion: Suggestion | None
) -> StaffDecision:
    """Derive the decision `escalate` that an escalation records.

    Args:
        request: The body of the escalation, valid already.
        suggestion: The current suggestion, when there is one.

    Returns:
        The decision, with the suggestion that the body names, when it names one.
    """
    return StaffDecision(
        DecisionType.ESCALATE,
        request.suggestion_id,
        request.staff_reason_codes,
        None,
        _final_intent(suggestion),
    )


def is_proposal_changed(sent: SentProposal) -> bool:
    """Tell whether a manager changed the proposed body, compared as a draft and a reply are.

    Args:
        sent: The proposal and the body that the manager sends.

    Returns:
        True when the normalized texts differ.
    """
    return normalize_reply_text(sent.proposal.request.body) != normalize_reply_text(sent.body)


def normalize_reply_text(text: str) -> str:
    """Normalize a text before a draft and a reply are compared.

    Args:
        text: The text.

    Returns:
        The text with LF line endings and without outer whitespace.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def compute_change_ratio(draft_text: str, body: str) -> float:
    """Compute how much a sent body differs from the draft (backend ticket workflow design).

    Args:
        draft_text: The canonical text of the draft, pseudonyms restored.
        body: The sent body.

    Returns:
        `1 - SequenceMatcher(None, draft, body).ratio()` over the normalized texts, rounded to
        three decimals: 0 for an unchanged draft, up to 1 for a rewrite.
    """
    draft = normalize_reply_text(draft_text)
    sent = normalize_reply_text(body)
    if draft == sent:
        return 0.0
    return round(1 - SequenceMatcher(None, draft, sent).ratio(), CHANGE_RATIO_DECIMALS)


def _derive_from_basis(
    basis: ProposalRequest, body: str, suggestion: Suggestion | None, draft_text: str | None
) -> StaffDecision | None:
    final_intent = _final_intent(suggestion)
    match basis:
        case AiDraftReply():
            # A valid `ai_draft` body always has a ready draft; the comparison is exact, so a
            # tiny edit that rounds to a ratio of 0 is still an edit.
            draft = draft_text or ""
            is_unchanged = normalize_reply_text(draft) == normalize_reply_text(body)
            return StaffDecision(
                DecisionType.APPROVE if is_unchanged else DecisionType.EDIT,
                basis.suggestion_id,
                basis.staff_reason_codes,
                compute_change_ratio(draft, body),
                final_intent,
            )
        case RejectedAiDraftReply():
            return StaffDecision(
                DecisionType.REJECT,
                basis.suggestion_id,
                basis.staff_reason_codes,
                None,
                final_intent,
            )
        case NoAiDraftReply():
            return None
        case _:
            assert_never(basis)


def _final_intent(suggestion: Suggestion | None) -> IntentLabel | None:
    return None if suggestion is None else suggestion.known_intent
