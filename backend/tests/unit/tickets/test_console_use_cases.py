"""Tests of the console use cases with fakes of every port (backend ticket workflow design).

Guardrail tests of TEST-26 are here: staff never send the reply of a ticket that requires
authority, also while a part is pending (FR-06), and no body with a placeholder is accepted
(SEC-38).
"""

import json
from dataclasses import replace
from uuid import UUID

import pytest

from supportiq_backend.accounts import (
    AccountId,
    CustomerId,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
    SupportPrincipal,
    SupportRole,
)
from supportiq_backend.audit import AuditEventType
from supportiq_backend.commerce import OrderId
from supportiq_backend.idempotency import IdempotencyKey, StoredResponse
from supportiq_backend.platform import EventName
from supportiq_backend.suggestions import (
    AiReasonCode,
    AiServiceContractError,
    AiServiceUnavailableError,
    InvalidTicketStateError,
    Suggestion,
    SuggestionPendingError,
    SuggestionTrigger,
)
from supportiq_backend.tickets import (
    AiDraftReply,
    AuthorityRequiredError,
    ConsoleTicket,
    DecisionType,
    GetConsoleTicket,
    HandlingMode,
    ListConsoleTickets,
    NoAiDraftReply,
    PlaceholderInBodyError,
    RecordTicketView,
    RejectedAiDraftReply,
    ReplyRecord,
    SendReply,
    StaffReasonCode,
    TicketAction,
    TicketId,
    TicketStatus,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START
from tests.unit.suggestions.builders import (
    OTHER_KB_VERSION,
    PREDICTED_INTENT,
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    build_draft_ready,
    build_failed_suggestion,
    build_ready_suggestion,
    build_suggestion,
    build_versions,
    with_override,
)
from tests.unit.suggestions.fakes import FakeAiService, FakeRestorer
from tests.unit.tickets.console_fakes import ConsoleHarness, build_console_harness

TICKET_ID = TicketId("TCK-1042")
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000123"))
STAFF = SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.STAFF)
MANAGER = SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.MANAGER)
DRAFT_TEXT = "Hello [NAME_1], your refund is under review."
RESTORED_DRAFT_TEXT = "Hello Lan Tran, your refund is under review."
RESTORER = FakeRestorer({"[NAME_1]": "Lan Tran"})


def build_ticket(
    *,
    status: TicketStatus = TicketStatus.OPEN,
    is_authority_required: bool = False,
    handling_mode: HandlingMode = HandlingMode.ASSISTED,
    handling_started_at: object = None,
) -> ConsoleTicket:
    return ConsoleTicket(
        ticket_id=TICKET_ID,
        status=status,
        handling_mode=handling_mode,
        is_authority_required=is_authority_required,
        created_at=FAKE_CLOCK_START,
        handling_started_at=FAKE_CLOCK_START if handling_started_at else None,
        closed_at=None,
        customer_id=CustomerId("00000000-0000-4000-8000-0000000000c1"),
        order_id=OrderId("ORD-20901"),
        current_suggestion_id=SUGGESTION_ID,
        message="Where is my refund?",
    )


def with_suggestion(harness: ConsoleHarness, suggestion: Suggestion) -> ConsoleHarness:
    harness.suggestions.data.add(suggestion)
    return harness


def render_reply(record: ReplyRecord) -> StoredResponse:
    return StoredResponse(201, json.dumps({"reply_id": str(record.reply.reply_id)}))


def build_send(harness: ConsoleHarness) -> SendReply:
    return SendReply(harness.transactions, harness.ports, render_reply)


def ai_draft_reply(body: str = RESTORED_DRAFT_TEXT) -> AiDraftReply:
    return AiDraftReply(body, SUGGESTION_ID, frozenset(), (), None)


@pytest.mark.anyio
async def test_staff_never_send_on_a_ticket_that_requires_authority_even_while_pending() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(is_authority_required=True)), build_suggestion()
    )

    with pytest.raises(AuthorityRequiredError):
        await build_send(harness).execute(STAFF, TICKET_ID, NoAiDraftReply("Hi", None), KEY)

    assert harness.replies.replies == {}
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.OPEN


@pytest.mark.anyio
async def test_a_manager_sends_the_reply_of_a_ticket_that_requires_authority() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(is_authority_required=True), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )

    await build_send(harness).execute(MANAGER, TICKET_ID, ai_draft_reply(), KEY)

    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.CLOSED


@pytest.mark.anyio
async def test_an_unchanged_restored_draft_is_sent_and_approved() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )

    await build_send(harness).execute(STAFF, TICKET_ID, ai_draft_reply(), KEY)

    (decision,) = harness.replies.decisions
    assert decision.decision.decision_type is DecisionType.APPROVE
    assert decision.decision.final_intent is PREDICTED_INTENT
    assert harness.replies.replies[TICKET_ID].body == RESTORED_DRAFT_TEXT
    assert [entry.event_type for entry in harness.audit.entries] == [
        AuditEventType.REPLY_SENT,
        AuditEventType.DECISION_RECORDED,
    ]
    assert EventName.REPLY_SENT in harness.events.names()


@pytest.mark.anyio
async def test_a_body_with_a_placeholder_is_refused_and_nothing_is_stored() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )

    with pytest.raises(PlaceholderInBodyError):
        await build_send(harness).execute(STAFF, TICKET_ID, ai_draft_reply(DRAFT_TEXT), KEY)

    assert harness.replies.replies == {}
    assert harness.transactions.commit_count == 0


@pytest.mark.anyio
async def test_a_repeated_reply_with_the_same_key_sends_nothing_more() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )
    send = build_send(harness)
    first = await send.execute(STAFF, TICKET_ID, ai_draft_reply(), KEY)

    repeated = await send.execute(STAFF, TICKET_ID, ai_draft_reply(), KEY)

    assert repeated == first
    assert len(harness.replies.decisions) == 1


@pytest.mark.anyio
async def test_a_pending_part_refuses_the_reply_of_a_manager() -> None:
    harness = with_suggestion(build_console_harness(build_ticket()), build_suggestion())

    with pytest.raises(SuggestionPendingError):
        await build_send(harness).execute(MANAGER, TICKET_ID, NoAiDraftReply("Hi", None), KEY)


@pytest.mark.anyio
async def test_a_closed_ticket_refuses_a_second_reply() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(status=TicketStatus.CLOSED)), build_ready_suggestion()
    )

    with pytest.raises(InvalidTicketStateError):
        await build_send(harness).execute(MANAGER, TICKET_ID, NoAiDraftReply("Hi", None), KEY)


@pytest.mark.parametrize(
    "principal",
    [
        CustomerPrincipal(AccountId("a1"), CustomerId("c1")),
        InternalPrincipal(AccountId("a2"), InternalRole.ADMIN),
    ],
)
def test_customers_and_admins_may_not_send_replies(
    principal: CustomerPrincipal | InternalPrincipal,
) -> None:
    harness = build_console_harness(build_ticket())

    with pytest.raises(ForbiddenRoleError):
        build_send(harness).authorize(principal)


@pytest.mark.anyio
async def test_the_first_view_starts_the_handling_clock_without_a_new_suggestion() -> None:
    harness = with_suggestion(build_console_harness(build_ticket()), build_ready_suggestion())

    await RecordTicketView(harness.transactions, harness.ports).execute(STAFF, TICKET_ID, KEY)

    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START
    assert harness.queue.notifications == []


@pytest.mark.anyio
async def test_the_first_view_reruns_a_suggestion_made_with_another_kb_version() -> None:
    harness = with_suggestion(
        build_console_harness(
            build_ticket(), ai_service=FakeAiService(versions=build_versions(OTHER_KB_VERSION))
        ),
        with_override(build_ready_suggestion(), PREDICTED_INTENT),
    )

    await RecordTicketView(harness.transactions, harness.ports).execute(STAFF, TICKET_ID, KEY)

    new = harness.suggestions.data.suggestions[harness.queue.notifications[0][1]]
    assert new.trigger is SuggestionTrigger.KB_VERSION_CHANGED
    assert new.intent_override is PREDICTED_INTENT


@pytest.mark.anyio
async def test_a_view_is_recorded_when_ai_service_does_not_answer_the_kb_read() -> None:
    harness = with_suggestion(
        build_console_harness(
            build_ticket(), ai_service=FakeAiService(versions=AiServiceUnavailableError())
        ),
        build_ready_suggestion(),
    )

    await RecordTicketView(harness.transactions, harness.ports).execute(STAFF, TICKET_ID, KEY)

    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START
    assert harness.queue.notifications == []
    assert EventName.AI_SERVICE_CALL_FAILED in harness.events.names()


@pytest.mark.anyio
async def test_a_kb_read_answered_outside_the_contract_is_logged_as_a_violation() -> None:
    harness = with_suggestion(
        build_console_harness(
            build_ticket(), ai_service=FakeAiService(versions=AiServiceContractError())
        ),
        build_ready_suggestion(),
    )

    await RecordTicketView(harness.transactions, harness.ports).execute(STAFF, TICKET_ID, KEY)

    (event,) = harness.events.of(EventName.AI_SERVICE_CONTRACT_VIOLATED)
    assert event.attributes["ai_service_operation"] == "getAssetVersions"
    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START


@pytest.mark.anyio
async def test_a_later_view_retries_a_suggestion_that_ai_service_failed() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(handling_started_at=True)),
        build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE),
    )

    await RecordTicketView(harness.transactions, harness.ports).execute(STAFF, TICKET_ID, KEY)

    new = harness.suggestions.data.suggestions[harness.queue.notifications[0][1]]
    assert new.trigger is SuggestionTrigger.RETRY


@pytest.mark.anyio
async def test_a_view_of_a_failed_pseudonymization_starts_nothing() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(handling_started_at=True)),
        build_failed_suggestion(AiReasonCode.PSEUDONYMIZATION_FAILED),
    )

    await RecordTicketView(harness.transactions, harness.ports).execute(STAFF, TICKET_ID, KEY)

    assert harness.queue.notifications == []


@pytest.mark.anyio
async def test_a_view_of_a_manual_ticket_never_calls_ai_service() -> None:
    harness = build_console_harness(
        replace(build_ticket(handling_mode=HandlingMode.MANUAL), current_suggestion_id=None),
        ai_service=FakeAiService(versions=AiServiceUnavailableError()),
    )

    await RecordTicketView(harness.transactions, harness.ports).execute(STAFF, TICKET_ID, KEY)

    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START
    assert harness.ai_service.requests == ()


@pytest.mark.anyio
async def test_staff_may_list_only_the_open_queue() -> None:
    harness = build_console_harness(build_ticket())
    principal = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.STAFF)
    use_case = ListConsoleTickets(harness.transactions, harness.ports)

    with pytest.raises(ForbiddenRoleError):
        await use_case.execute(principal, TicketStatus.CLOSED, None, 10)


@pytest.mark.anyio
async def test_the_workspace_restores_the_draft_and_names_the_allowed_actions() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )
    principal = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.STAFF)

    workspace = await GetConsoleTicket(harness.transactions, harness.ports).execute(
        principal, TICKET_ID
    )

    assert workspace.suggestion is not None
    assert workspace.suggestion.draft_text == RESTORED_DRAFT_TEXT
    assert TicketAction.SEND_REPLY in workspace.allowed_actions
    assert harness.transactions.commit_count == 0


@pytest.mark.anyio
async def test_a_manager_lists_a_queue_with_the_customer_and_the_suggestion() -> None:
    harness = with_suggestion(build_console_harness(build_ticket()), build_ready_suggestion())
    principal = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.MANAGER)

    page = await ListConsoleTickets(harness.transactions, harness.ports).execute(
        principal, TicketStatus.OPEN, None, 10
    )

    (summary,) = page.items
    assert summary.customer_display_name == "Lan Tran"
    assert summary.suggestion is not None
    assert page.next_position is None


@pytest.mark.anyio
async def test_a_rejected_draft_records_the_staff_reason_codes() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )
    reply = RejectedAiDraftReply(
        "We checked your order.", SUGGESTION_ID, (StaffReasonCode.WRONG_INTENT,), None
    )

    await build_send(harness).execute(STAFF, TICKET_ID, reply, KEY)

    (decision,) = harness.replies.decisions
    assert decision.decision.decision_type is DecisionType.REJECT
    assert harness.audit.entries[-1].data["staff_reason_codes"] == "wrong_intent"


@pytest.mark.anyio
async def test_a_reply_without_a_draft_records_no_decision() -> None:
    harness = with_suggestion(
        build_console_harness(build_ticket()),
        build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE),
    )

    await build_send(harness).execute(STAFF, TICKET_ID, NoAiDraftReply("Hi", SUGGESTION_ID), KEY)

    assert harness.replies.decisions == []
    assert harness.replies.replies[TICKET_ID].suggestion_id == SUGGESTION_ID
