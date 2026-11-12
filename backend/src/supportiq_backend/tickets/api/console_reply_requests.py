"""Read the body of `sendReply` into the domain request, once, at the boundary (CODE-32).

The basis of the body chooses the variant. A repeated item of an array that the contract
marks `uniqueItems: true` is refused, so a repeated warning ID never stands in for another.
"""

from typing import assert_never
from uuid import UUID

from pydantic import MISSING

from supportiq_backend.generated import (
    AiDraftReplyRequest,
    NoAiDraftReplyRequest,
    RejectedAiDraftReplyRequest,
    ReplyProposalReplyRequest,
    StaffNoteText,
)
from supportiq_backend.generated import StaffReasonCode as ContractStaffReasonCode
from supportiq_backend.platform import RequestContractError
from supportiq_backend.suggestions import SuggestionId
from supportiq_backend.tickets.api.console_request_fields import (
    parse_storable_text,
    parse_unique_items,
)
from supportiq_backend.tickets.domain import (
    AiDraftReply,
    NoAiDraftReply,
    ProposalId,
    ProposalReply,
    RejectedAiDraftReply,
    ReplyRequest,
    StaffReasonCode,
)

_BODY_LOCATION = "body.body"
_WARNINGS_LOCATION = "body.acknowledged_warning_ids"
_REASON_CODES_LOCATION = "body.staff_reason_codes"
_NOTE_LOCATION = "body.note"
_PROPOSAL_LOCATION = "body.proposal_id"

# The variants of `SendReplyRequest`, discriminated by `basis`.
type ReplyRequestBody = (
    AiDraftReplyRequest
    | RejectedAiDraftReplyRequest
    | NoAiDraftReplyRequest
    | ReplyProposalReplyRequest
)


def parse_reply_request(body: ReplyRequestBody) -> ReplyRequest:
    """Turn a reply body of the contract into the domain request.

    Args:
        body: The parsed body, discriminated by `basis`.

    Returns:
        The domain request.

    Raises:
        RequestContractError: A text cannot be stored, an array repeats an item, or the
            proposal ID is not a UUID.
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
            return NoAiDraftReply(
                text, None if body.suggestion_id is MISSING else SuggestionId(body.suggestion_id)
            )
        case ReplyProposalReplyRequest():
            return ProposalReply(text, _parse_proposal_id(body.proposal_id))
        case _:
            assert_never(body)


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


def _parse_proposal_id(raw: str) -> ProposalId:
    try:
        return ProposalId(UUID(raw))
    except ValueError as error:
        raise RequestContractError((_PROPOSAL_LOCATION,)) from error
