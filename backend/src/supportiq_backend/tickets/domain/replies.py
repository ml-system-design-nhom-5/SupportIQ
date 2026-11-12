"""Replies, their bases, and the staff decision they record (contracts v1 design, ADR-0006).

A reply body and a staff note are Confidential, so the classes that hold them have no
generated `repr` (LOG-29). A decision holds no text.
"""

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from enum import StrEnum
from typing import NewType, assert_never
from uuid import UUID

from supportiq_backend.accounts import AccountId
from supportiq_backend.platform import InvalidRequestError
from supportiq_backend.pseudonymization import contains_placeholder
from supportiq_backend.suggestions import (
    Analysis,
    IntentLabel,
    Suggestion,
    SuggestionId,
    get_part_status,
)
from supportiq_backend.tickets.domain.console import ConsoleTicket
from supportiq_backend.tickets.domain.tickets import TicketId, TicketStatus

ReplyId = NewType("ReplyId", UUID)
ProposalId = NewType("ProposalId", UUID)
DecisionId = NewType("DecisionId", UUID)

# `change_ratio` has three decimals: 0 for an unchanged draft, up to 1 for a rewrite.
CHANGE_RATIO_DECIMALS = 3
_PARAGRAPH_SEPARATOR = "\n\n"
_SEGMENT_SEPARATOR = " "
_NO_DRAFT_STATUS = "absent"


class ReplyBasis(StrEnum):
    """What a reply is based on (contracts v1 design, `sendReply`)."""

    AI_DRAFT = "ai_draft"
    REJECTED_AI_DRAFT = "rejected_ai_draft"
    NO_AI_DRAFT = "no_ai_draft"
    REPLY_PROPOSAL = "reply_proposal"


class StaffReasonCode(StrEnum):
    """Why staff edited, rejected, or escalated (ADR-0006)."""

    WRONG_INTENT = "wrong_intent"
    WRONG_SOURCE = "wrong_source"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    KB_GAP = "kb_gap"
    MISSING_CASE_INFO = "missing_case_info"
    TONE_OR_CLARITY = "tone_or_clarity"
    CASE_EXCEPTION = "case_exception"
    OTHER = "other"


class DecisionType(StrEnum):
    """What staff or a manager did with a suggestion (ADR-0006)."""

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True, repr=False)
class AiDraftReply:
    """A reply based on the current draft, sent as is or edited.

    Attributes:
        body: The text that the customer reads.
        suggestion_id: The suggestion of the draft.
        acknowledged_warning_ids: Every warning of that suggestion.
        staff_reason_codes: Why staff edited, when they say.
        note: A note for the record, required with `other`.
    """

    body: str
    suggestion_id: SuggestionId
    acknowledged_warning_ids: frozenset[str]
    staff_reason_codes: tuple[StaffReasonCode, ...]
    note: str | None


@dataclass(frozen=True, slots=True, repr=False)
class RejectedAiDraftReply:
    """A reply written instead of a ready draft that staff rejected.

    Attributes:
        body: The text that the customer reads.
        suggestion_id: The suggestion of the rejected draft.
        staff_reason_codes: Why staff rejected it, at least one.
        note: A note for the record, required with `other`.
    """

    body: str
    suggestion_id: SuggestionId
    staff_reason_codes: tuple[StaffReasonCode, ...]
    note: str | None


@dataclass(frozen=True, slots=True, repr=False)
class NoAiDraftReply:
    """A reply without a ready draft, or on a ticket in manual mode.

    Attributes:
        body: The text that the customer reads.
        suggestion_id: The current suggestion, when staff name it.
    """

    body: str
    suggestion_id: SuggestionId | None


@dataclass(frozen=True, slots=True, repr=False)
class ProposalReply:
    """A manager's reply from a reply proposal, as proposed or edited.

    Attributes:
        body: The text that the customer reads.
        proposal_id: The proposal.
    """

    body: str
    proposal_id: ProposalId


type ReplyRequest = AiDraftReply | RejectedAiDraftReply | NoAiDraftReply | ProposalReply


@dataclass(frozen=True, slots=True)
class StaffDecision:
    """The decision that a reply records about a draft; it holds no text (ADR-0006).

    Attributes:
        decision_type: Approve, edit, or reject.
        suggestion_id: The suggestion of the draft.
        staff_reason_codes: The staff reason codes of the reply.
        change_ratio: How much the body differs from the draft, in [0, 1].
        final_intent: The intent of the suggestion, staff-chosen after an override.
    """

    decision_type: DecisionType
    suggestion_id: SuggestionId
    staff_reason_codes: tuple[StaffReasonCode, ...]
    change_ratio: float | None
    final_intent: IntentLabel | None


@dataclass(frozen=True, slots=True)
class RecordedDecision:
    """A staff decision as `staff_decisions` stores it, once (ADR-0006).

    Attributes:
        decision_id: The identifier.
        ticket_id: The ticket.
        decision: What was decided about the draft.
        decided_by: The account that sent the reply.
        proposed_by: The staff member who proposed it, for a reply from a proposal.
        is_proposal_changed: Whether the manager changed the proposed body.
        decided_at: When the reply was sent.
    """

    decision_id: DecisionId
    ticket_id: TicketId
    decision: StaffDecision
    decided_by: AccountId
    proposed_by: AccountId | None
    is_proposal_changed: bool | None
    decided_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class SentReply:
    """A reply as stored and as the console shows it.

    Attributes:
        reply_id: The identifier.
        ticket_id: The ticket.
        basis: What it is based on.
        body: The text that the customer reads.
        suggestion_id: The suggestion it names, when it names one.
        proposal_id: The proposal it comes from, when it comes from one.
        acknowledged_warning_ids: The warnings that the sender acknowledged.
        staff_reason_codes: The staff reason codes.
        note: The note, when there is one.
        sent_by: The account that sent it.
        sent_at: When it was sent.
    """

    reply_id: ReplyId
    ticket_id: TicketId
    basis: ReplyBasis
    body: str
    suggestion_id: SuggestionId | None
    proposal_id: ProposalId | None
    acknowledged_warning_ids: tuple[str, ...]
    staff_reason_codes: tuple[StaffReasonCode, ...]
    note: str | None
    sent_by: AccountId
    sent_at: datetime


class ReplyBasisInvalidError(InvalidRequestError):
    """The basis of a reply is not valid for the ticket and its current draft (422)."""

    def __init__(self, basis: ReplyBasis, draft_status: str) -> None:
        """Build the error from the basis and the draft status.

        Args:
            basis: The basis of the body.
            draft_status: The status of the current draft, or `absent`.
        """
        super().__init__(
            f"The basis {basis.value} is not valid while the current draft is {draft_status}."
        )


class WarningsNotAcknowledgedError(InvalidRequestError):
    """A reply based on a draft does not acknowledge every warning of its suggestion (422)."""

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__(
            "Every warning of the suggestion must be acknowledged in acknowledged_warning_ids."
        )


class NoteRequiredError(InvalidRequestError):
    """`staff_reason_codes` contains `other` and the note is absent (422)."""

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("A note is required when staff_reason_codes contains other.")


class PlaceholderInBodyError(InvalidRequestError):
    """A reply or proposal body contains a placeholder, which never reaches a customer (422)."""

    def __init__(self) -> None:
        """Build the error with its fixed detail (SEC-38)."""
        super().__init__(
            "The body contains a placeholder. Replace it with the text that the customer should"
            " read."
        )


def validate_reply_body(
    ticket: ConsoleTicket, suggestion: Suggestion | None, reply: ReplyRequest
) -> None:
    """Run step 8 of the check order: the body rules of the basis.

    The rules run in the order of the design: the basis, the warnings, the note, and the
    placeholder.

    Args:
        ticket: The ticket.
        suggestion: Its current suggestion, when it has one.
        reply: The body of the request.

    Raises:
        ReplyBasisInvalidError: The basis is not valid for the ticket or its draft.
        WarningsNotAcknowledgedError: A warning of the draft is not acknowledged.
        NoteRequiredError: `other` without a note.
        PlaceholderInBodyError: The body contains a placeholder (SEC-38).
    """
    _validate_basis(ticket, suggestion, reply)
    match reply:
        case AiDraftReply():
            if reply.acknowledged_warning_ids != _warning_ids(suggestion):
                raise WarningsNotAcknowledgedError
            _validate_note(reply.staff_reason_codes, reply.note)
        case RejectedAiDraftReply():
            _validate_note(reply.staff_reason_codes, reply.note)
        case NoAiDraftReply() | ProposalReply():
            pass
        case _:
            assert_never(reply)
    if contains_placeholder(reply.body):
        raise PlaceholderInBodyError


def derive_decision(
    reply: ReplyRequest, suggestion: Suggestion | None, draft_text: str | None
) -> StaffDecision | None:
    """Derive the decision that a reply records (contracts v1 design, Recorded decision).

    Args:
        reply: The body of the request, valid already.
        suggestion: The current suggestion, when there is one.
        draft_text: The canonical text of its ready draft, pseudonyms restored.

    Returns:
        `approve` or `edit` for a reply on a draft, `reject` for a rejected draft, and None
        for a reply without a draft.
    """
    final_intent = None if suggestion is None else suggestion.known_intent
    match reply:
        case AiDraftReply():
            # A valid `ai_draft` reply always has a ready draft; the comparison is exact, so
            # a tiny edit that rounds to a ratio of 0 is still an edit.
            draft = draft_text or ""
            is_unchanged = normalize_reply_text(draft) == normalize_reply_text(reply.body)
            change_ratio = compute_change_ratio(draft, reply.body)
            decision_type = DecisionType.APPROVE if is_unchanged else DecisionType.EDIT
            return StaffDecision(
                decision_type,
                reply.suggestion_id,
                reply.staff_reason_codes,
                change_ratio,
                final_intent,
            )
        case RejectedAiDraftReply():
            return StaffDecision(
                DecisionType.REJECT,
                reply.suggestion_id,
                reply.staff_reason_codes,
                None,
                final_intent,
            )
        case NoAiDraftReply() | ProposalReply():
            return None
        case _:
            assert_never(reply)


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


def build_draft_text(segments: tuple[tuple[int, str], ...]) -> str:
    """Join draft segments into the canonical plain-text body (contracts v1 design).

    Segments of one paragraph are joined by one space, and paragraphs by one blank line.

    Args:
        segments: The paragraph index and the restored text of each segment, in order.

    Returns:
        The canonical text.
    """
    paragraphs: list[list[str]] = []
    last_index: int | None = None
    for paragraph_index, text in segments:
        if paragraph_index != last_index:
            paragraphs.append([])
            last_index = paragraph_index
        paragraphs[-1].append(text)
    return _PARAGRAPH_SEPARATOR.join(_SEGMENT_SEPARATOR.join(parts) for parts in paragraphs)


def _validate_basis(
    ticket: ConsoleTicket, suggestion: Suggestion | None, reply: ReplyRequest
) -> None:
    has_ready_draft = suggestion is not None and suggestion.ready_draft is not None
    is_awaiting_approval = ticket.status is TicketStatus.AWAITING_APPROVAL
    match reply:
        case AiDraftReply() | RejectedAiDraftReply():
            is_valid = has_ready_draft and not is_awaiting_approval
        case NoAiDraftReply():
            is_valid = not has_ready_draft and not is_awaiting_approval
        case ProposalReply():
            is_valid = is_awaiting_approval
        case _:
            assert_never(reply)
    if not is_valid:
        raise ReplyBasisInvalidError(_basis_of(reply), _draft_status_name(suggestion))


def _validate_note(staff_reason_codes: tuple[StaffReasonCode, ...], note: str | None) -> None:
    if StaffReasonCode.OTHER in staff_reason_codes and note is None:
        raise NoteRequiredError


def _warning_ids(suggestion: Suggestion | None) -> frozenset[str]:
    # The warnings that the workspace shows: those of the analysis part, from the analysis
    # call or, when that call failed, from the draft response. Two calls may name their
    # warnings differently, so the analysis inside the draft response never decides.
    if suggestion is None or not isinstance(suggestion.analysis, Analysis):
        return frozenset()
    return frozenset(warning.warning_id for warning in suggestion.analysis.warnings)


def _basis_of(reply: ReplyRequest) -> ReplyBasis:
    match reply:
        case AiDraftReply():
            return ReplyBasis.AI_DRAFT
        case RejectedAiDraftReply():
            return ReplyBasis.REJECTED_AI_DRAFT
        case NoAiDraftReply():
            return ReplyBasis.NO_AI_DRAFT
        case ProposalReply():
            return ReplyBasis.REPLY_PROPOSAL
        case _:
            assert_never(reply)


def _draft_status_name(suggestion: Suggestion | None) -> str:
    if suggestion is None:
        return _NO_DRAFT_STATUS
    return get_part_status(suggestion.draft).value
