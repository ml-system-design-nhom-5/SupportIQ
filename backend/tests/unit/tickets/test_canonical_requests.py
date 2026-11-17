"""The canonical form of the console's action requests, which idempotency compares (ERR-15).

An array that the contract marks `uniqueItems: true` is a set: the same items in another
order are the same request, and other items are another request.
"""

from collections.abc import Callable

import pytest

from supportiq_backend.tickets import (
    AiDraftReply,
    EscalationRequest,
    RejectedAiDraftReply,
    ReplyRequest,
    StaffReasonCode,
)
from supportiq_backend.tickets.application.canonical_requests import (
    to_canonical_escalation,
    to_canonical_reply,
)
from tests.unit.suggestions.builders import SUGGESTION_ID
from tests.unit.tickets.console_fakes import TICKET_ID

type ReplyOf = Callable[[tuple[StaffReasonCode, ...]], ReplyRequest]

BODY = "We checked your order and the refund is on its way."
CODES = (StaffReasonCode.TONE_OR_CLARITY, StaffReasonCode.KB_GAP)
REORDERED_CODES = (StaffReasonCode.KB_GAP, StaffReasonCode.TONE_OR_CLARITY)
OTHER_CODES = (StaffReasonCode.KB_GAP,)


def on_the_draft(codes: tuple[StaffReasonCode, ...]) -> ReplyRequest:
    return AiDraftReply(BODY, SUGGESTION_ID, frozenset({"w2", "w1"}), codes, None)


def rejecting_the_draft(codes: tuple[StaffReasonCode, ...]) -> ReplyRequest:
    return RejectedAiDraftReply(BODY, SUGGESTION_ID, codes, None)


REPLIES_WITH_CODES = pytest.mark.parametrize(
    "reply_of", [on_the_draft, rejecting_the_draft], ids=["ai-draft", "rejected-ai-draft"]
)


@REPLIES_WITH_CODES
def test_reason_codes_in_another_order_are_the_same_reply_request(reply_of: ReplyOf) -> None:
    first = to_canonical_reply(TICKET_ID, reply_of(CODES))

    reordered = to_canonical_reply(TICKET_ID, reply_of(REORDERED_CODES))

    assert reordered == first


@REPLIES_WITH_CODES
def test_other_reason_codes_are_another_reply_request(reply_of: ReplyOf) -> None:
    first = to_canonical_reply(TICKET_ID, reply_of(CODES))

    other = to_canonical_reply(TICKET_ID, reply_of(OTHER_CODES))

    assert other != first


def test_reason_codes_in_another_order_are_the_same_escalation_request() -> None:
    first = to_canonical_escalation(TICKET_ID, EscalationRequest(CODES, None, None))

    reordered = to_canonical_escalation(TICKET_ID, EscalationRequest(REORDERED_CODES, None, None))

    assert reordered == first


def test_other_reason_codes_are_another_escalation_request() -> None:
    first = to_canonical_escalation(TICKET_ID, EscalationRequest(CODES, None, None))

    other = to_canonical_escalation(TICKET_ID, EscalationRequest(OTHER_CODES, None, None))

    assert other != first
