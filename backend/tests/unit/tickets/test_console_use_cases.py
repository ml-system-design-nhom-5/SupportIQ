"""Tests of the console use cases with fakes of every port (backend ticket workflow design).

Guardrail tests of TEST-26 are here: staff never send the reply of a ticket that requires
authority, also while a part is pending (FR-06), and no body with a placeholder is accepted
(SEC-38).
"""

import pytest

from supportiq_backend.accounts import ForbiddenRoleError, Principal
from supportiq_backend.audit import AuditEventType
from supportiq_backend.commerce import AddressedOrder
from supportiq_backend.platform import EventName
from supportiq_backend.suggestions import (
    AiReasonCode,
    AiServiceContractError,
    AiServiceUnavailableError,
    InvalidTicketStateError,
    SuggestionPendingError,
    SuggestionTrigger,
)
from supportiq_backend.tickets import (
    AiDraftReply,
    AuthorityRequiredError,
    DecisionType,
    HandlingMode,
    NoAiDraftReply,
    PlaceholderInBodyError,
    RejectedAiDraftReply,
    StaffReasonCode,
    TicketAction,
    TicketStatus,
)
from supportiq_backend.tickets.domain import OTHER_ORDERS_LIMIT
from tests.unit.commerce.fakes import build_order
from tests.unit.platform.fakes import FAKE_CLOCK_START
from tests.unit.pseudonymization.fakes import REFERENCES
from tests.unit.suggestions.builders import (
    OTHER_KB_VERSION,
    PREDICTED_INTENT,
    SUGGESTION_ID,
    build_draft_ready,
    build_failed_suggestion,
    build_ready_suggestion,
    build_suggestion,
    build_versions,
    with_override,
)
from tests.unit.suggestions.fakes import FakeAiService, FakeRestorer
from tests.unit.tickets.console_fakes import (
    ADMIN,
    CUSTOMER,
    KEY,
    MANAGER,
    SIGNED_IN_STAFF,
    STAFF,
    TICKET_ID,
    build_console_harness,
    build_console_ticket,
    build_get,
    build_list,
    build_send,
    build_view,
    with_suggestion,
)

DRAFT_TEXT = "Hello [NAME_1], your refund is under review."
RESTORED_DRAFT_TEXT = "Hello Lan Tran, your refund is under review."
RESTORER = FakeRestorer({"[NAME_1]": "Lan Tran"})


def ai_draft_reply(body: str = RESTORED_DRAFT_TEXT) -> AiDraftReply:
    return AiDraftReply(body, SUGGESTION_ID, frozenset(), (), None)


def addressed(order_id: str) -> AddressedOrder:
    return AddressedOrder(build_order(order_id), REFERENCES.shipping_address)


@pytest.mark.anyio
async def test_staff_never_send_on_a_ticket_that_requires_authority_even_while_pending() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(is_authority_required=True)),
        build_suggestion(),
    )

    with pytest.raises(AuthorityRequiredError):
        await build_send(harness).execute(STAFF, TICKET_ID, NoAiDraftReply("Hi", None), KEY)

    assert harness.replies.replies == {}
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.OPEN


@pytest.mark.anyio
async def test_a_manager_sends_the_reply_of_a_ticket_that_requires_authority() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(is_authority_required=True), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )

    await build_send(harness).execute(MANAGER, TICKET_ID, ai_draft_reply(), KEY)

    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.CLOSED


@pytest.mark.anyio
async def test_an_unchanged_restored_draft_is_sent_and_approved() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(), restorer=RESTORER),
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
        build_console_harness(build_console_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )

    with pytest.raises(PlaceholderInBodyError):
        await build_send(harness).execute(STAFF, TICKET_ID, ai_draft_reply(DRAFT_TEXT), KEY)

    assert harness.replies.replies == {}
    assert harness.transactions.commit_count == 0


@pytest.mark.anyio
async def test_a_repeated_reply_with_the_same_key_sends_nothing_more() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )
    send = build_send(harness)
    first = await send.execute(STAFF, TICKET_ID, ai_draft_reply(), KEY)

    repeated = await send.execute(STAFF, TICKET_ID, ai_draft_reply(), KEY)

    assert repeated == first
    assert len(harness.replies.decisions) == 1


@pytest.mark.anyio
async def test_a_pending_part_refuses_the_reply_of_a_manager() -> None:
    harness = with_suggestion(build_console_harness(build_console_ticket()), build_suggestion())

    with pytest.raises(SuggestionPendingError):
        await build_send(harness).execute(MANAGER, TICKET_ID, NoAiDraftReply("Hi", None), KEY)


@pytest.mark.anyio
async def test_a_closed_ticket_refuses_a_second_reply() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(status=TicketStatus.CLOSED)),
        build_ready_suggestion(),
    )

    with pytest.raises(InvalidTicketStateError):
        await build_send(harness).execute(MANAGER, TICKET_ID, NoAiDraftReply("Hi", None), KEY)


@pytest.mark.parametrize("principal", [CUSTOMER, ADMIN])
def test_customers_and_admins_may_not_send_replies(principal: Principal) -> None:
    harness = build_console_harness(build_console_ticket())

    with pytest.raises(ForbiddenRoleError):
        build_send(harness).authorize(principal)


@pytest.mark.anyio
async def test_the_first_view_starts_the_handling_clock_without_a_new_suggestion() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket()), build_ready_suggestion()
    )

    await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START
    assert harness.queue.notifications == []


@pytest.mark.anyio
async def test_the_first_view_reruns_a_suggestion_made_with_another_kb_version() -> None:
    harness = with_suggestion(
        build_console_harness(
            build_console_ticket(),
            ai_service=FakeAiService(versions=build_versions(OTHER_KB_VERSION)),
        ),
        with_override(build_ready_suggestion(), PREDICTED_INTENT),
    )

    await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    new = harness.suggestions.data.suggestions[harness.queue.notifications[0][1]]
    assert new.trigger is SuggestionTrigger.KB_VERSION_CHANGED
    assert new.intent_override is PREDICTED_INTENT


@pytest.mark.anyio
async def test_a_view_is_recorded_when_ai_service_does_not_answer_the_kb_read() -> None:
    harness = with_suggestion(
        build_console_harness(
            build_console_ticket(), ai_service=FakeAiService(versions=AiServiceUnavailableError())
        ),
        build_ready_suggestion(),
    )

    await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START
    assert harness.queue.notifications == []
    assert EventName.AI_SERVICE_CALL_FAILED in harness.events.names()


@pytest.mark.anyio
async def test_a_kb_read_answered_outside_the_contract_is_logged_as_a_violation() -> None:
    harness = with_suggestion(
        build_console_harness(
            build_console_ticket(), ai_service=FakeAiService(versions=AiServiceContractError())
        ),
        build_ready_suggestion(),
    )

    await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    (event,) = harness.events.of(EventName.AI_SERVICE_CONTRACT_VIOLATED)
    assert event.attributes["ai_service_operation"] == "getAssetVersions"
    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START


@pytest.mark.anyio
async def test_a_later_view_retries_a_suggestion_that_ai_service_failed() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(handling_started_at=FAKE_CLOCK_START)),
        build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE),
    )

    await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    new = harness.suggestions.data.suggestions[harness.queue.notifications[0][1]]
    assert new.trigger is SuggestionTrigger.RETRY


@pytest.mark.anyio
async def test_a_view_of_a_failed_pseudonymization_starts_nothing() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(handling_started_at=FAKE_CLOCK_START)),
        build_failed_suggestion(AiReasonCode.PSEUDONYMIZATION_FAILED),
    )

    await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    assert harness.queue.notifications == []


@pytest.mark.anyio
async def test_a_first_view_of_a_manual_ticket_with_a_suggestion_calls_no_ai_service() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(handling_mode=HandlingMode.MANUAL)),
        build_ready_suggestion(),
    )

    await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START
    assert harness.ai_service.version_reads == 0
    assert harness.ai_service.requests == ()
    assert harness.queue.notifications == []
    assert list(harness.suggestions.data.suggestions) == [SUGGESTION_ID]


@pytest.mark.anyio
async def test_a_first_view_of_a_ticket_without_a_suggestion_calls_no_ai_service() -> None:
    harness = build_console_harness(build_console_ticket())

    await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    assert harness.tickets.tickets[TICKET_ID].handling_started_at == FAKE_CLOCK_START
    assert harness.ai_service.version_reads == 0
    assert harness.ai_service.requests == ()
    assert harness.queue.notifications == []


@pytest.mark.anyio
async def test_staff_may_list_only_the_open_queue() -> None:
    harness = build_console_harness(build_console_ticket())

    with pytest.raises(ForbiddenRoleError):
        await build_list(harness).execute(STAFF, TicketStatus.CLOSED, None, 10)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": STAFF.account_id,
        "role": "staff",
        "operation_id": "listConsoleTickets",
    }


@pytest.mark.anyio
async def test_the_workspace_restores_the_draft_and_names_the_allowed_actions() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(), restorer=RESTORER),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )

    workspace = await build_get(harness).execute(SIGNED_IN_STAFF, TICKET_ID)

    assert workspace.suggestion is not None
    assert workspace.suggestion.draft_text == RESTORED_DRAFT_TEXT
    assert TicketAction.SEND_REPLY in workspace.allowed_actions
    assert harness.transactions.commit_count == 0


@pytest.mark.anyio
async def test_the_workspace_loads_at_most_the_limit_of_other_orders() -> None:
    harness = build_console_harness(build_console_ticket())
    ticket_order = addressed(REFERENCES.order_id)
    other_orders = tuple(
        addressed(f"ORD-{30_001 + number}") for number in range(OTHER_ORDERS_LIMIT + 1)
    )
    harness.records.orders = (ticket_order, *other_orders)

    workspace = await build_get(harness).execute(SIGNED_IN_STAFF, TICKET_ID)

    assert workspace.order == ticket_order
    assert workspace.other_orders == tuple(item.order for item in other_orders[:OTHER_ORDERS_LIMIT])


@pytest.mark.anyio
async def test_a_manager_lists_a_queue_with_the_customer_and_the_suggestion() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket()), build_ready_suggestion()
    )

    page = await build_list(harness).execute(MANAGER, TicketStatus.OPEN, None, 10)

    (summary,) = page.items
    assert summary.customer_display_name == "Lan Tran"
    assert summary.suggestion is not None
    assert page.next_position is None


@pytest.mark.anyio
async def test_a_rejected_draft_records_the_staff_reason_codes() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(), restorer=RESTORER),
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
        build_console_harness(build_console_ticket()),
        build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE),
    )

    await build_send(harness).execute(STAFF, TICKET_ID, NoAiDraftReply("Hi", SUGGESTION_ID), KEY)

    assert harness.replies.decisions == []
    assert harness.replies.replies[TICKET_ID].suggestion_id == SUGGESTION_ID
