"""Replies, the body rules of their bases, and the canonical text of a draft (contracts v1 design).

A reply body and a staff note are Confidential, so the classes that hold them have no
generated `repr` (LOG-29).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import NewType, assert_never
from uuid import UUID

from supportiq_backend.accounts import AccountId
from supportiq_backend.platform import InvalidRequestError
from supportiq_backend.pseudonymization import contains_placeholder
from supportiq_backend.suggestions import (
    Analysis,
    Suggestion,
    SuggestionId,
    get_part_status,
)
from supportiq_backend.tickets.domain.console import ConsoleTicket
from supportiq_backend.tickets.domain.proposals import ReplyProposal, ResolvedReply, SentProposal
from supportiq_backend.tickets.domain.reply_requests import (
    AiDraftReply,
    NoAiDraftReply,
    ProposalId,
    ProposalReply,
    RejectedAiDraftReply,
    ReplyBasis,
    StaffReasonCode,
)
from supportiq_backend.tickets.domain.tickets import TicketId, TicketStatus

ReplyId = NewType("ReplyId", UUID)

_PARAGRAPH_SEPARATOR = "\n\n"
_SEGMENT_SEPARATOR = " "
_NO_DRAFT_STATUS = "absent"
# Why `reply_proposal` is refused when the body names no proposal of the ticket (contract
# `InvalidReply`: "`reply_proposal` with another proposal").
_OTHER_PROPOSAL = "with a proposal_id that is not the proposal of the ticket"


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
    """The basis of a reply is not valid for the ticket: its draft or its proposal (422)."""

    def __init__(self, basis: ReplyBasis, reason: str) -> None:
        """Build the error from the basis and why the ticket refuses it.

        Args:
            basis: The basis of the body.
            reason: The end of the detail, from statuses only, such as `while the current
                draft is draft_ready`.
        """
        super().__init__(f"The basis {basis.value} is not valid {reason}.")


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


def parse_sent_proposal(reply: ProposalReply, proposal: ReplyProposal | None) -> SentProposal:
    """Turn a manager's reply on a proposal into the ticket's proposal and the body it sends.

    This is the first rule of the basis `reply_proposal`, in step 8 of the check order.

    Args:
        reply: The body of the request.
        proposal: The proposal of the ticket, or None when it has none.

    Returns:
        The proposal with the body that the manager sends.

    Raises:
        ReplyBasisInvalidError: The body names another proposal, or the ticket has none.
    """
    if proposal is None or proposal.proposal_id != reply.proposal_id:
        raise ReplyBasisInvalidError(ReplyBasis.REPLY_PROPOSAL, _OTHER_PROPOSAL)
    return SentProposal(proposal, reply.body)


def validate_reply_body(
    ticket: ConsoleTicket, suggestion: Suggestion | None, reply: ResolvedReply
) -> None:
    """Run step 8 of the check order: the body rules of the basis.

    The rules run in the order of the design: the basis, the warnings, the note, and the
    placeholder. A reply proposal follows the same rules as the reply that it stands for.

    Args:
        ticket: The ticket.
        suggestion: Its current suggestion, when it has one.
        reply: The body of the request, with the proposal that it sends resolved.

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
            validate_staff_note(reply.staff_reason_codes, reply.note)
        case RejectedAiDraftReply():
            validate_staff_note(reply.staff_reason_codes, reply.note)
        case NoAiDraftReply() | SentProposal():
            pass
        case _:
            assert_never(reply)
    if contains_placeholder(reply.body):
        raise PlaceholderInBodyError


def validate_staff_note(staff_reason_codes: tuple[StaffReasonCode, ...], note: str | None) -> None:
    """Check that staff wrote a note when a reason code is `other` (ADR-0006).

    Args:
        staff_reason_codes: The staff reason codes of the body.
        note: The staff note, when there is one.

    Raises:
        NoteRequiredError: `other` without a note.
    """
    if StaffReasonCode.OTHER in staff_reason_codes and note is None:
        raise NoteRequiredError


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
    ticket: ConsoleTicket, suggestion: Suggestion | None, reply: ResolvedReply
) -> None:
    has_ready_draft = suggestion is not None and suggestion.ready_draft is not None
    is_awaiting_approval = ticket.status is TicketStatus.AWAITING_APPROVAL
    match reply:
        case AiDraftReply() | RejectedAiDraftReply():
            is_valid = has_ready_draft and not is_awaiting_approval
        case NoAiDraftReply():
            is_valid = not has_ready_draft and not is_awaiting_approval
        case SentProposal():
            is_valid = is_awaiting_approval
        case _:
            assert_never(reply)
    if not is_valid:
        draft_status = _draft_status_name(suggestion)
        raise ReplyBasisInvalidError(reply.basis, f"while the current draft is {draft_status}")


def _warning_ids(suggestion: Suggestion | None) -> frozenset[str]:
    # The warnings that the workspace shows: those of the analysis part, from the analysis
    # call or, when that call failed, from the draft response. Two calls may name their
    # warnings differently, so the analysis inside the draft response never decides.
    if suggestion is None or not isinstance(suggestion.analysis, Analysis):
        return frozenset()
    return frozenset(warning.warning_id for warning in suggestion.analysis.warnings)


def _draft_status_name(suggestion: Suggestion | None) -> str:
    if suggestion is None:
        return _NO_DRAFT_STATUS
    return get_part_status(suggestion.draft).value
