"""Tests of `createEscalation` with fakes of every port (backend ticket workflow design).

Staff escalate an `open` ticket, also while a suggestion part is pending, and the escalation
records the staff decision `escalate` (ADR-0006). The AI only recommends; this staff action
decides. A reason `other` needs a note.
"""

import pytest

from supportiq_backend.accounts import ForbiddenRoleError, Principal
from supportiq_backend.audit import AuditEventType
from supportiq_backend.idempotency import IdempotencyKeyReusedError
from supportiq_backend.platform import EventName
from supportiq_backend.suggestions import (
    InvalidTicketStateError,
    SuggestionId,
    SuggestionSupersededError,
)
from supportiq_backend.tickets import (
    DecisionType,
    EscalationRequest,
    HandlingMode,
    NoteRequiredError,
    StaffDecision,
    StaffReasonCode,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START
from tests.unit.suggestions.builders import (
    PREDICTED_INTENT,
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    build_ready_suggestion,
    build_suggestion,
)
from tests.unit.tickets.console_fakes import (
    ADMIN,
    CUSTOMER,
    KEY,
    SIGNED_IN_MANAGER,
    STAFF,
    TICKET_ID,
    ConsoleHarness,
    build_console_harness,
    build_console_ticket,
    build_escalate,
    with_suggestion,
)
from tests.unit.tickets.fakes import MANAGER_ACCOUNT_ID

pytestmark = pytest.mark.anyio

NOTE = "The customer asks to talk to a person."
OTHER_SUGGESTION_ID = SuggestionId("00000000-0000-4000-8000-000000000002")
UNKNOWN_TICKET_ID = TicketId("TCK-9999")
NOT_OPEN = [TicketStatus.AWAITING_APPROVAL, TicketStatus.ESCALATED, TicketStatus.CLOSED]
REFUSED_ROLES = [(CUSTOMER, "customer"), (ADMIN, "admin")]
ESCALATION = EscalationRequest((StaffReasonCode.CASE_EXCEPTION,), None, SUGGESTION_ID)
WITHOUT_SUGGESTION = EscalationRequest((StaffReasonCode.CASE_EXCEPTION,), None, None)


def harness_with_suggestion() -> ConsoleHarness:
    return with_suggestion(build_console_harness(build_console_ticket()), build_ready_suggestion())


def assert_nothing_escalated(harness: ConsoleHarness) -> None:
    assert harness.escalations.escalations == {}
    assert harness.replies.decisions == []
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.OPEN
    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.TICKET_ESCALATED) == ()


async def test_staff_escalate_an_open_ticket_to_the_manager_queue() -> None:
    harness = harness_with_suggestion()

    await build_escalate(harness).execute(STAFF, TICKET_ID, ESCALATION, KEY)

    escalation = harness.escalations.escalations[TICKET_ID]
    assert (escalation.escalated_by, escalation.escalated_at) == (
        STAFF_ACCOUNT_ID,
        FAKE_CLOCK_START,
    )
    assert escalation.request.staff_reason_codes == (StaffReasonCode.CASE_EXCEPTION,)
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.ESCALATED


async def test_an_escalation_records_the_decision_escalate() -> None:
    harness = harness_with_suggestion()

    await build_escalate(harness).execute(STAFF, TICKET_ID, ESCALATION, KEY)

    (recorded,) = harness.replies.decisions
    assert recorded.decision == StaffDecision(
        DecisionType.ESCALATE,
        SUGGESTION_ID,
        (StaffReasonCode.CASE_EXCEPTION,),
        None,
        PREDICTED_INTENT,
    )
    assert (recorded.decided_by, recorded.proposed_by, recorded.is_proposal_changed) == (
        STAFF_ACCOUNT_ID,
        None,
        None,
    )


async def test_an_escalation_writes_its_audit_entries_with_identifiers_only() -> None:
    harness = harness_with_suggestion()

    await build_escalate(harness).execute(STAFF, TICKET_ID, ESCALATION, KEY)

    escalated, decided = harness.audit.entries
    assert (escalated.event_type, escalated.actor_account_id) == (
        AuditEventType.TICKET_ESCALATED,
        STAFF_ACCOUNT_ID,
    )
    assert escalated.data == {
        "escalation_id": str(harness.escalations.escalations[TICKET_ID].escalation_id),
        "staff_reason_codes": "case_exception",
        "suggestion_id": SUGGESTION_ID,
    }
    assert decided.event_type is AuditEventType.DECISION_RECORDED
    assert decided.data == {
        "decision_type": "escalate",
        "staff_reason_codes": "case_exception",
        "suggestion_id": SUGGESTION_ID,
    }


async def test_an_escalation_records_its_events_after_the_commit() -> None:
    harness = harness_with_suggestion()

    await build_escalate(harness).execute(STAFF, TICKET_ID, ESCALATION, KEY)

    (escalated,) = harness.events.of(EventName.TICKET_ESCALATED)
    (decided,) = harness.events.of(EventName.DECISION_RECORDED)
    assert escalated.attributes == {"ticket_id": TICKET_ID}
    assert decided.attributes == {
        "ticket_id": TICKET_ID,
        "suggestion_id": SUGGESTION_ID,
        "decision_type": "escalate",
    }


async def test_an_escalation_without_a_suggestion_id_names_none() -> None:
    harness = harness_with_suggestion()

    await build_escalate(harness).execute(STAFF, TICKET_ID, WITHOUT_SUGGESTION, KEY)

    (recorded,) = harness.replies.decisions
    (decided,) = harness.events.of(EventName.DECISION_RECORDED)
    assert recorded.decision.suggestion_id is None
    assert recorded.decision.final_intent is PREDICTED_INTENT
    assert "suggestion_id" not in harness.audit.entries[0].data
    assert decided.attributes == {"ticket_id": TICKET_ID, "decision_type": "escalate"}


async def test_staff_escalate_while_a_suggestion_part_is_pending() -> None:
    harness = with_suggestion(build_console_harness(build_console_ticket()), build_suggestion())

    await build_escalate(harness).execute(STAFF, TICKET_ID, ESCALATION, KEY)

    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.ESCALATED


async def test_a_manual_ticket_is_escalated_without_a_final_intent() -> None:
    harness = build_console_harness(build_console_ticket(handling_mode=HandlingMode.MANUAL))

    await build_escalate(harness).execute(STAFF, TICKET_ID, WITHOUT_SUGGESTION, KEY)

    (recorded,) = harness.replies.decisions
    assert recorded.decision.final_intent is None
    assert harness.ai_service.requests == ()


async def test_other_with_a_note_is_escalated_with_the_note() -> None:
    harness = harness_with_suggestion()
    escalation = EscalationRequest((StaffReasonCode.OTHER,), NOTE, None)

    await build_escalate(harness).execute(STAFF, TICKET_ID, escalation, KEY)

    assert harness.escalations.escalations[TICKET_ID].request.note == NOTE


async def test_other_without_a_note_is_refused_and_nothing_is_stored() -> None:
    harness = harness_with_suggestion()
    escalation = EscalationRequest((StaffReasonCode.OTHER,), None, None)

    with pytest.raises(NoteRequiredError):
        await build_escalate(harness).execute(STAFF, TICKET_ID, escalation, KEY)

    assert_nothing_escalated(harness)


@pytest.mark.parametrize("status", NOT_OPEN)
async def test_a_ticket_that_is_not_open_refuses_an_escalation(status: TicketStatus) -> None:
    harness = build_console_harness(build_console_ticket(status=status))

    with pytest.raises(InvalidTicketStateError):
        await build_escalate(harness).execute(STAFF, TICKET_ID, WITHOUT_SUGGESTION, KEY)

    assert harness.escalations.escalations == {}
    assert harness.tickets.tickets[TICKET_ID].status is status


async def test_the_state_is_checked_before_the_note() -> None:
    harness = build_console_harness(build_console_ticket(status=TicketStatus.ESCALATED))
    escalation = EscalationRequest((StaffReasonCode.OTHER,), None, None)

    with pytest.raises(InvalidTicketStateError):
        await build_escalate(harness).execute(STAFF, TICKET_ID, escalation, KEY)


async def test_a_superseded_suggestion_is_refused_before_the_note() -> None:
    harness = harness_with_suggestion()
    escalation = EscalationRequest((StaffReasonCode.OTHER,), None, OTHER_SUGGESTION_ID)

    with pytest.raises(SuggestionSupersededError):
        await build_escalate(harness).execute(STAFF, TICKET_ID, escalation, KEY)

    assert_nothing_escalated(harness)


async def test_an_escalation_for_an_unknown_ticket_is_not_found() -> None:
    harness = harness_with_suggestion()

    with pytest.raises(TicketNotFoundError):
        await build_escalate(harness).execute(STAFF, UNKNOWN_TICKET_ID, ESCALATION, KEY)

    assert_nothing_escalated(harness)


async def test_a_repeated_escalation_with_the_same_key_records_nothing_more() -> None:
    harness = harness_with_suggestion()
    escalate = build_escalate(harness)
    first = await escalate.execute(STAFF, TICKET_ID, ESCALATION, KEY)

    repeated = await escalate.execute(STAFF, TICKET_ID, ESCALATION, KEY)

    assert repeated == first
    assert len(harness.replies.decisions) == 1
    assert len(harness.events.of(EventName.TICKET_ESCALATED)) == 1


async def test_a_key_reused_with_other_reasons_is_refused() -> None:
    harness = harness_with_suggestion()
    escalate = build_escalate(harness)
    await escalate.execute(STAFF, TICKET_ID, ESCALATION, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await escalate.execute(STAFF, TICKET_ID, WITHOUT_SUGGESTION, KEY)

    assert harness.escalations.escalations[TICKET_ID].request.suggestion_id == SUGGESTION_ID


async def test_a_manager_may_not_escalate_and_the_refusal_is_recorded() -> None:
    harness = harness_with_suggestion()

    with pytest.raises(ForbiddenRoleError):
        build_escalate(harness).authorize(SIGNED_IN_MANAGER)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": MANAGER_ACCOUNT_ID,
        "role": "manager",
        "operation_id": "createEscalation",
    }


@pytest.mark.parametrize(("principal", "role"), REFUSED_ROLES)
async def test_customers_and_admins_may_not_escalate(principal: Principal, role: str) -> None:
    harness = harness_with_suggestion()

    with pytest.raises(ForbiddenRoleError):
        build_escalate(harness).authorize(principal)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert (denied.attributes["role"], denied.attributes["operation_id"]) == (
        role,
        "createEscalation",
    )
