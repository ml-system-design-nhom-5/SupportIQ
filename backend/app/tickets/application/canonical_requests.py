"""The canonical form of the console's action requests, for their idempotency records (ERR-15).

A retry with the same `Idempotency-Key` and request returns the original response, and the
same key with another request is refused. Each form holds the path parameter and every body
field as a scalar, so two requests that differ in any field differ in their form. An array
that the contract marks `uniqueItems: true` is a set, so its items are sorted: the same items
in another order are the same request.
"""

from collections.abc import Iterable, Mapping
from typing import assert_never

from app.idempotency import CanonicalValue
from app.tickets.application.console_actions import LIST_SEPARATOR
from app.tickets.domain import (
    AiDraftReply,
    EscalationRequest,
    NoAiDraftReply,
    ProposalReply,
    RejectedAiDraftReply,
    ReplyRequest,
    StaffReasonCode,
    TicketId,
)

# The value of an absent optional identifier: an identifier of the contract is never empty.
_ABSENT = ""


def to_canonical_reply(ticket_id: TicketId, reply: ReplyRequest) -> Mapping[str, CanonicalValue]:
    """Build the canonical form of a reply or reply proposal request.

    Args:
        ticket_id: The path parameter.
        reply: The body, parsed.

    Returns:
        The body fields and the path parameter as scalars.
    """
    fields: dict[str, CanonicalValue] = {"ticket_id": ticket_id, "body": reply.body}
    match reply:
        case AiDraftReply():
            fields.update(
                basis=reply.basis.value,
                suggestion_id=reply.suggestion_id,
                acknowledged_warning_ids=_join_unique_items(reply.acknowledged_warning_ids),
                staff_reason_codes=_join_reason_codes(reply.staff_reason_codes),
                **_note_fields(reply.note),
            )
        case RejectedAiDraftReply():
            fields.update(
                basis=reply.basis.value,
                suggestion_id=reply.suggestion_id,
                staff_reason_codes=_join_reason_codes(reply.staff_reason_codes),
                **_note_fields(reply.note),
            )
        case NoAiDraftReply():
            fields.update(basis=reply.basis.value, suggestion_id=reply.suggestion_id or _ABSENT)
        case ProposalReply():
            fields.update(basis=reply.basis.value, proposal_id=reply.proposal_id)
        case _:
            assert_never(reply)
    return fields


def to_canonical_escalation(
    ticket_id: TicketId, escalation: EscalationRequest
) -> Mapping[str, CanonicalValue]:
    """Build the canonical form of an escalation request.

    Args:
        ticket_id: The path parameter.
        escalation: The body, parsed.

    Returns:
        The body fields and the path parameter as scalars.
    """
    return {
        "ticket_id": ticket_id,
        "staff_reason_codes": _join_reason_codes(escalation.staff_reason_codes),
        "suggestion_id": escalation.suggestion_id or _ABSENT,
        **_note_fields(escalation.note),
    }


def _join_reason_codes(codes: tuple[StaffReasonCode, ...]) -> str:
    return _join_unique_items(code.value for code in codes)


def _join_unique_items(items: Iterable[str]) -> str:
    # The items of a `uniqueItems` array are a set, so their order never makes another request.
    return LIST_SEPARATOR.join(sorted(items))


def _note_fields(note: str | None) -> Mapping[str, CanonicalValue]:
    return {"note": note or _ABSENT, "has_note": note is not None}
