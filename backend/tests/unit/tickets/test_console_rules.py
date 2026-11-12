"""Tests of the console rules: allowed actions, the check order, bases, and decisions."""

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from supportiq_backend.accounts import ForbiddenRoleError, SupportRole
from supportiq_backend.suggestions import (
    AiReasonCode,
    InvalidTicketStateError,
    NoDraftStatus,
    SuggestionId,
    SuggestionPendingError,
    SuggestionSupersededError,
)
from supportiq_backend.tickets import (
    AiDraftReply,
    AuthorityRequiredError,
    ConsoleTicket,
    DecisionType,
    HandlingMode,
    NoAiDraftReply,
    NoteRequiredError,
    PlaceholderInBodyError,
    RejectedAiDraftReply,
    ReplyBasisInvalidError,
    StaffReasonCode,
    TicketAction,
    TicketStatus,
    WarningsNotAcknowledgedError,
    build_draft_text,
    check_reply_allowed,
    check_suggestion_is_current,
    compute_allowed_actions,
    compute_change_ratio,
    derive_decision,
    validate_reply_body,
)
from tests.unit.suggestions.builders import (
    PREDICTED_INTENT,
    SUGGESTION_ID,
    build_analysis,
    build_draft_ready,
    build_failed_suggestion,
    build_no_draft,
    build_ready_suggestion,
    build_suggestion,
)
from tests.unit.tickets.console_fakes import build_console_ticket

DRAFT_TEXT = "Hello Lan, your refund is under review."
STAFF = SupportRole.STAFF
MANAGER = SupportRole.MANAGER
OTHER_SUGGESTION_ID = SuggestionId("00000000-0000-4000-8000-000000000002")
NO_ACTION: set[TicketAction] = set()


def build_ticket(
    status: TicketStatus = TicketStatus.OPEN,
    *,
    is_authority_required: bool = False,
    handling_mode: HandlingMode = HandlingMode.ASSISTED,
) -> ConsoleTicket:
    ticket = build_console_ticket(
        status=status, handling_mode=handling_mode, is_authority_required=is_authority_required
    )
    return replace(ticket, current_suggestion_id=SUGGESTION_ID)


def ai_draft_reply(body: str = DRAFT_TEXT, **changes: object) -> AiDraftReply:
    reply = AiDraftReply(body, SUGGESTION_ID, frozenset(), (), None)
    return replace(reply, **changes)


@pytest.mark.parametrize(
    ("status", "role", "expected"),
    [
        (
            TicketStatus.OPEN,
            STAFF,
            {
                TicketAction.SEND_REPLY,
                TicketAction.SUBMIT_REPLY_PROPOSAL,
                TicketAction.ESCALATE,
                TicketAction.CORRECT_INTENT,
            },
        ),
        (TicketStatus.OPEN, MANAGER, {TicketAction.SEND_REPLY, TicketAction.CORRECT_INTENT}),
        (TicketStatus.AWAITING_APPROVAL, STAFF, NO_ACTION),
        (TicketStatus.AWAITING_APPROVAL, MANAGER, {TicketAction.SEND_REPLY}),
        (TicketStatus.ESCALATED, MANAGER, {TicketAction.SEND_REPLY}),
        (TicketStatus.CLOSED, MANAGER, NO_ACTION),
        (TicketStatus.CLOSED, STAFF, NO_ACTION),
    ],
)
def test_allowed_actions_follow_the_state_and_the_role(
    status: TicketStatus, role: SupportRole, expected: set[TicketAction]
) -> None:
    actions = compute_allowed_actions(build_ticket(status), build_ready_suggestion(), role)

    assert actions == expected


def test_staff_may_not_send_on_a_ticket_that_requires_authority() -> None:
    ticket = build_ticket(is_authority_required=True)

    actions = compute_allowed_actions(ticket, build_ready_suggestion(), STAFF)

    assert TicketAction.SEND_REPLY not in actions
    assert TicketAction.SUBMIT_REPLY_PROPOSAL in actions


def test_a_pending_part_blocks_sending_and_proposing_but_not_escalating() -> None:
    actions = compute_allowed_actions(build_ticket(), build_suggestion(), STAFF)

    assert actions == {TicketAction.ESCALATE}


def test_a_failed_suggestion_offers_a_retry_and_no_intent_correction() -> None:
    suggestion = build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE)

    actions = compute_allowed_actions(build_ticket(), suggestion, STAFF)

    assert TicketAction.RETRY_SUGGESTION in actions
    assert TicketAction.CORRECT_INTENT not in actions


def test_a_failed_pseudonymization_offers_no_retry() -> None:
    suggestion = build_failed_suggestion(AiReasonCode.PSEUDONYMIZATION_FAILED)

    actions = compute_allowed_actions(build_ticket(), suggestion, STAFF)

    assert TicketAction.RETRY_SUGGESTION not in actions


def test_a_manual_ticket_offers_no_ai_action() -> None:
    ticket = build_ticket(handling_mode=HandlingMode.MANUAL)

    actions = compute_allowed_actions(ticket, None, STAFF)

    assert actions == {
        TicketAction.SEND_REPLY,
        TicketAction.SUBMIT_REPLY_PROPOSAL,
        TicketAction.ESCALATE,
    }


def test_a_closed_ticket_refuses_a_reply_first() -> None:
    with pytest.raises(InvalidTicketStateError):
        check_reply_allowed(build_ticket(TicketStatus.CLOSED), build_suggestion(), MANAGER)


@pytest.mark.parametrize("status", [TicketStatus.AWAITING_APPROVAL, TicketStatus.ESCALATED])
def test_staff_may_not_send_on_a_ticket_that_waits_for_a_manager(status: TicketStatus) -> None:
    with pytest.raises(ForbiddenRoleError):
        check_reply_allowed(build_ticket(status), None, STAFF)


def test_authority_comes_before_a_pending_part_for_staff() -> None:
    ticket = build_ticket(is_authority_required=True)

    with pytest.raises(AuthorityRequiredError):
        check_reply_allowed(ticket, build_suggestion(), STAFF)


def test_a_manager_may_send_on_a_ticket_that_requires_authority() -> None:
    ticket = build_ticket(is_authority_required=True)

    check_reply_allowed(ticket, build_ready_suggestion(), MANAGER)

    assert ticket.is_authority_required


def test_a_pending_part_refuses_a_reply() -> None:
    with pytest.raises(SuggestionPendingError):
        check_reply_allowed(build_ticket(), build_suggestion(), MANAGER)


def test_a_body_that_names_another_suggestion_is_superseded() -> None:
    with pytest.raises(SuggestionSupersededError):
        check_suggestion_is_current(build_ticket(), OTHER_SUGGESTION_ID)


def test_a_body_without_a_suggestion_id_passes_the_currency_check() -> None:
    check_suggestion_is_current(build_ticket(), None)

    assert build_ticket().current_suggestion_id == SUGGESTION_ID


def test_no_ai_draft_is_refused_while_the_draft_is_ready() -> None:
    with pytest.raises(ReplyBasisInvalidError) as caught:
        validate_reply_body(build_ticket(), build_ready_suggestion(), NoAiDraftReply("Hi", None))

    assert caught.value.detail == (
        "The basis no_ai_draft is not valid while the current draft is draft_ready."
    )


def test_ai_draft_is_refused_without_a_ready_draft() -> None:
    suggestion = build_ready_suggestion(build_no_draft(NoDraftStatus.ABSTAINED))

    with pytest.raises(ReplyBasisInvalidError):
        validate_reply_body(build_ticket(), suggestion, ai_draft_reply())


def test_every_warning_must_be_acknowledged() -> None:
    suggestion = build_suggestion(
        analysis=build_analysis(warning_ids=("w1", "w2")), draft=build_draft_ready()
    )

    with pytest.raises(WarningsNotAcknowledgedError):
        validate_reply_body(
            build_ticket(), suggestion, ai_draft_reply(acknowledged_warning_ids=frozenset({"w1"}))
        )


def test_the_warnings_to_acknowledge_are_those_of_the_analysis_part_that_staff_see() -> None:
    suggestion = build_suggestion(
        analysis=build_analysis(warning_ids=("analysis-w1",)),
        draft=build_draft_ready(warning_ids=("draft-w1",)),
    )
    reply = ai_draft_reply(acknowledged_warning_ids=frozenset({"analysis-w1"}))

    validate_reply_body(build_ticket(), suggestion, reply)


def test_a_warning_of_the_analysis_inside_the_draft_response_is_not_the_one_shown() -> None:
    suggestion = build_suggestion(
        analysis=build_analysis(warning_ids=("analysis-w1",)),
        draft=build_draft_ready(warning_ids=("draft-w1",)),
    )

    with pytest.raises(WarningsNotAcknowledgedError):
        validate_reply_body(
            build_ticket(),
            suggestion,
            ai_draft_reply(acknowledged_warning_ids=frozenset({"draft-w1"})),
        )


def test_other_needs_a_note() -> None:
    reply = RejectedAiDraftReply("Hi", SUGGESTION_ID, (StaffReasonCode.OTHER,), None)

    with pytest.raises(NoteRequiredError):
        validate_reply_body(build_ticket(), build_ready_suggestion(), reply)


@pytest.mark.parametrize(
    "body", ["Hi [NAME_1]", "Order [ORDER_ID_12]", "Mail [EMAIL]", "Was [LITERAL_1]"]
)
def test_a_body_with_a_placeholder_is_refused(body: str) -> None:
    with pytest.raises(PlaceholderInBodyError):
        validate_reply_body(build_ticket(), None, NoAiDraftReply(body, None))


def test_a_body_with_brackets_that_are_no_placeholder_is_accepted() -> None:
    reply = NoAiDraftReply("See [the attached note] and [NAME_0].", None)

    validate_reply_body(build_ticket(), None, reply)

    assert reply.body.startswith("See")


def test_an_unchanged_draft_is_approved_with_no_change() -> None:
    decision = derive_decision(
        ai_draft_reply(f"  {DRAFT_TEXT}\r\n"), build_ready_suggestion(), DRAFT_TEXT
    )

    assert decision is not None
    assert decision.decision_type is DecisionType.APPROVE
    assert decision.change_ratio == 0
    assert decision.final_intent is PREDICTED_INTENT


def test_an_edited_draft_is_an_edit_with_its_amount_of_change() -> None:
    decision = derive_decision(
        ai_draft_reply("Hello Lan, your refund was paid."), build_ready_suggestion(), DRAFT_TEXT
    )

    assert decision is not None
    assert decision.decision_type is DecisionType.EDIT
    assert decision.change_ratio is not None
    assert 0 < decision.change_ratio < 1


def test_a_tiny_edit_of_a_long_draft_is_still_an_edit() -> None:
    long_draft = "a" * 5_000

    decision = derive_decision(
        ai_draft_reply(long_draft + "b"), build_ready_suggestion(), long_draft
    )

    assert decision is not None
    assert decision.decision_type is DecisionType.EDIT


def test_a_rejected_draft_records_reject_and_no_draft_records_nothing() -> None:
    rejected = RejectedAiDraftReply("Hi", SUGGESTION_ID, (StaffReasonCode.WRONG_INTENT,), None)

    assert derive_decision(rejected, build_ready_suggestion(), DRAFT_TEXT) is not None
    assert derive_decision(NoAiDraftReply("Hi", None), None, None) is None


@given(st.text(max_size=200))
def test_change_ratio_is_zero_for_equal_texts(text: str) -> None:
    assert compute_change_ratio(text, text) == 0


@given(st.text(max_size=200), st.text(max_size=200))
def test_change_ratio_is_between_zero_and_one(draft: str, body: str) -> None:
    assert 0 <= compute_change_ratio(draft, body) <= 1


def test_draft_text_joins_segments_with_a_space_and_paragraphs_with_a_blank_line() -> None:
    text = build_draft_text(((0, "Hello Lan."), (1, "Your refund"), (1, "is under review.")))

    assert text == "Hello Lan.\n\nYour refund is under review."
