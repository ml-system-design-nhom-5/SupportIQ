"""Read the bodies of the console's actions into domain requests, once, at the boundary.

`sendReply` and `createReplyProposal` take a body whose basis chooses the variant, and
`createEscalation` takes its reasons (CODE-32). A repeated item of an array that the contract
marks `uniqueItems: true` is refused, so a repeated warning ID never stands in for another.
A `proposal_id` stays the string that the request sent: identifiers are opaque, so it is
compared with the ticket's proposal in step 8 of the check order and never parsed (CON-15).
"""

from typing import assert_never

from pydantic import MISSING

from app.generated import (
    AiDraftReplyRequest,
    CreateEscalationRequest,
    NoAiDraftReplyRequest,
    RejectedAiDraftReplyRequest,
    ReplyProposalReplyRequest,
    StaffNoteText,
)
from app.generated import StaffReasonCode as ContractStaffReasonCode
from app.suggestions import SuggestionId
from app.tickets.api.console_request_fields import (
    parse_storable_text,
    parse_unique_items,
)
from app.tickets.domain import (
    AiDraftReply,
    EscalationRequest,
    NoAiDraftReply,
    ProposalReply,
    ProposalRequest,
    RejectedAiDraftReply,
    ReplyRequest,
    StaffReasonCode,
)

_BODY_LOCATION = "body.body"
_WARNINGS_LOCATION = "body.acknowledged_warning_ids"
_REASON_CODES_LOCATION = "body.staff_reason_codes"
_NOTE_LOCATION = "body.note"

# The variants of `CreateReplyProposalRequest`, discriminated by `basis`.
type ProposalRequestBody = AiDraftReplyRequest | RejectedAiDraftReplyRequest | NoAiDraftReplyRequest
# The variants of `SendReplyRequest`, discriminated by `basis`.
type ReplyRequestBody = ProposalRequestBody | ReplyProposalReplyRequest


def parse_reply_request(body: ReplyRequestBody) -> ReplyRequest:
    """Turn a reply body of the contract into the domain request.

    Args:
        body: The parsed body, discriminated by `basis`.

    Returns:
        The domain request.

    Raises:
        RequestContractError: A text cannot be stored, or an array repeats an item.
    """
    match body:
        case ReplyProposalReplyRequest():
            return ProposalReply(
                parse_storable_text(body.body.root.root, _BODY_LOCATION), body.proposal_id
            )
        case AiDraftReplyRequest() | RejectedAiDraftReplyRequest() | NoAiDraftReplyRequest():
            return parse_proposal_request(body)
        case _:
            assert_never(body)


def parse_proposal_request(body: ProposalRequestBody) -> ProposalRequest:
    """Turn a body on a draft, or without one, into the domain request.

    It is the body of `createReplyProposal`, and every body of `sendReply` but a proposal's.

    Args:
        body: The parsed body, discriminated by `basis`.

    Returns:
        The domain request.

    Raises:
        RequestContractError: A text cannot be stored, or an array repeats an item.
    """
    text = parse_storable_text(body.body.root.root, _BODY_LOCATION)
    match body:
        case AiDraftReplyRequest():
            return _parse_ai_draft_reply(body, text)
        case RejectedAiDraftReplyRequest():
            return RejectedAiDraftReply(
                body=text,
                suggestion_id=SuggestionId(body.suggestion_id),
                staff_reason_codes=_parse_reason_codes(body.staff_reason_codes),
                note=_parse_note(body.note),
            )
        case NoAiDraftReplyRequest():
            return NoAiDraftReply(text, _parse_suggestion_id(body.suggestion_id))
        case _:
            assert_never(body)


def parse_escalation_request(body: CreateEscalationRequest) -> EscalationRequest:
    """Turn the body of `createEscalation` into the domain request.

    Args:
        body: The parsed body.

    Returns:
        The domain request.

    Raises:
        RequestContractError: The note cannot be stored, or a reason code repeats.
    """
    return EscalationRequest(
        staff_reason_codes=_parse_reason_codes(body.staff_reason_codes),
        note=_parse_note(body.note),
        suggestion_id=_parse_suggestion_id(body.suggestion_id),
    )


def _parse_ai_draft_reply(body: AiDraftReplyRequest, text: str) -> AiDraftReply:
    warning_ids = parse_unique_items(
        (item.root for item in body.acknowledged_warning_ids), _WARNINGS_LOCATION
    )
    return AiDraftReply(
        body=text,
        suggestion_id=SuggestionId(body.suggestion_id),
        acknowledged_warning_ids=frozenset(warning_ids),
        staff_reason_codes=(
            ()
            if body.staff_reason_codes is MISSING
            else _parse_reason_codes(body.staff_reason_codes)
        ),
        note=_parse_note(body.note),
    )


def _parse_reason_codes(codes: list[ContractStaffReasonCode]) -> tuple[StaffReasonCode, ...]:
    unique_codes = parse_unique_items(codes, _REASON_CODES_LOCATION)
    return tuple(StaffReasonCode(code.value) for code in unique_codes)


def _parse_note(note: StaffNoteText | MISSING) -> str | None:
    return None if note is MISSING else parse_storable_text(note.root, _NOTE_LOCATION)


def _parse_suggestion_id(raw: str | MISSING) -> SuggestionId | None:
    return None if raw is MISSING else SuggestionId(raw)
