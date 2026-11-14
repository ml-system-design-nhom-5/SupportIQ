"""Refusals and failures of the console use cases with fakes of every port (SEC-41, ERR-15).

Customers and admins never reach a console use case, and an unknown ticket, a reused
`Idempotency-Key`, or an unavailable database changes nothing and records no event of success
(backend ticket workflow design, Ticket state machine and check order).
"""

from collections.abc import Callable

import pytest

from supportiq_backend.accounts import ForbiddenRoleError, Principal
from supportiq_backend.idempotency import IdempotencyKeyReusedError
from supportiq_backend.platform import DatabaseUnavailableError, EventName
from supportiq_backend.tickets import (
    EscalationRequest,
    NoAiDraftReply,
    ProposalReply,
    StaffReasonCode,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
)
from tests.unit.suggestions.builders import build_ready_suggestion
from tests.unit.tickets.console_fakes import (
    ADMIN,
    CUSTOMER,
    KEY,
    MANAGER,
    SIGNED_IN_MANAGER,
    STAFF,
    TICKET_ID,
    ConsoleHarness,
    build_console_harness,
    build_console_ticket,
    build_escalate,
    build_get,
    build_list,
    build_propose,
    build_send,
    build_view,
    with_suggestion,
)

pytestmark = pytest.mark.anyio

OTHER_TICKET_ID = TicketId("TCK-1043")
UNKNOWN_TICKET_ID = TicketId("TCK-9999")
REFUSED_ROLES = [(CUSTOMER, "customer"), (ADMIN, "admin")]
PAGE_LIMIT = 10
REPLY = NoAiDraftReply("Your parcel left our warehouse today.", None)
OTHER_REPLY = NoAiDraftReply("Your parcel arrives tomorrow.", None)
ESCALATION = EscalationRequest((StaffReasonCode.CASE_EXCEPTION,), None, None)


def with_failing_suggestion_store(harness: ConsoleHarness) -> ConsoleHarness:
    with_suggestion(harness, build_ready_suggestion())
    harness.suggestions.failure = DatabaseUnavailableError()
    return harness


def fail_proposal_store(harness: ConsoleHarness) -> None:
    harness.proposals.failure = DatabaseUnavailableError()


def fail_escalation_store(harness: ConsoleHarness) -> None:
    harness.escalations.failure = DatabaseUnavailableError()


@pytest.mark.parametrize(("principal", "role"), REFUSED_ROLES)
async def test_list_console_tickets_refuses_customers_and_admins_and_records_it(
    principal: Principal, role: str
) -> None:
    harness = build_console_harness(build_console_ticket())

    with pytest.raises(ForbiddenRoleError):
        build_list(harness).authorize(principal)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": principal.account_id,
        "role": role,
        "operation_id": "listConsoleTickets",
    }


@pytest.mark.parametrize(("principal", "role"), REFUSED_ROLES)
async def test_get_console_ticket_refuses_customers_and_admins_before_any_read(
    principal: Principal, role: str
) -> None:
    harness = build_console_harness(build_console_ticket())

    with pytest.raises(ForbiddenRoleError):
        await build_get(harness).execute(principal, TICKET_ID)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert (denied.attributes["role"], denied.attributes["operation_id"]) == (
        role,
        "getConsoleTicket",
    )
    assert harness.transactions.rollback_count == 0


@pytest.mark.parametrize(("principal", "role"), REFUSED_ROLES)
async def test_record_ticket_view_refuses_customers_and_admins_and_records_it(
    principal: Principal, role: str
) -> None:
    harness = build_console_harness(build_console_ticket())

    with pytest.raises(ForbiddenRoleError):
        build_view(harness).authorize(principal)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert (denied.attributes["role"], denied.attributes["operation_id"]) == (
        role,
        "recordTicketView",
    )


async def test_record_ticket_view_returns_a_manager_as_support() -> None:
    harness = build_console_harness(build_console_ticket())

    support = build_view(harness).authorize(SIGNED_IN_MANAGER)

    assert support == MANAGER
    assert harness.events.of(EventName.PERMISSION_DENIED) == ()


async def test_workspace_of_an_unknown_ticket_is_not_found() -> None:
    harness = build_console_harness(build_console_ticket())

    with pytest.raises(TicketNotFoundError):
        await build_get(harness).execute(SIGNED_IN_MANAGER, UNKNOWN_TICKET_ID)


async def test_view_of_an_unknown_ticket_is_not_found_and_records_nothing() -> None:
    harness = build_console_harness(build_console_ticket())

    with pytest.raises(TicketNotFoundError):
        await build_view(harness).execute(STAFF, UNKNOWN_TICKET_ID, KEY)

    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.TICKET_VIEWED) == ()


async def test_reply_to_an_unknown_ticket_is_not_found_and_sends_nothing() -> None:
    harness = build_console_harness(build_console_ticket())

    with pytest.raises(TicketNotFoundError):
        await build_send(harness).execute(STAFF, UNKNOWN_TICKET_ID, REPLY, KEY)

    assert harness.replies.replies == {}
    assert harness.transactions.commit_count == 0


async def test_view_key_reused_on_another_ticket_is_refused_and_starts_no_clock() -> None:
    harness = build_console_harness(build_console_ticket(), build_console_ticket(OTHER_TICKET_ID))
    view = build_view(harness)
    await view.execute(STAFF, TICKET_ID, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await view.execute(STAFF, OTHER_TICKET_ID, KEY)

    assert harness.tickets.tickets[OTHER_TICKET_ID].handling_started_at is None
    assert len(harness.events.of(EventName.TICKET_VIEWED)) == 1


async def test_reply_key_reused_with_another_body_is_refused_and_keeps_the_first_reply() -> None:
    harness = build_console_harness(build_console_ticket())
    send = build_send(harness)
    await send.execute(STAFF, TICKET_ID, REPLY, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await send.execute(STAFF, TICKET_ID, OTHER_REPLY, KEY)

    assert harness.replies.replies[TICKET_ID].body == REPLY.body
    assert len(harness.events.of(EventName.REPLY_SENT)) == 1


async def test_unavailable_database_reaches_the_queue() -> None:
    harness = with_failing_suggestion_store(build_console_harness(build_console_ticket()))

    with pytest.raises(DatabaseUnavailableError):
        await build_list(harness).execute(MANAGER, TicketStatus.OPEN, None, PAGE_LIMIT)


async def test_unavailable_database_reaches_the_workspace() -> None:
    harness = with_failing_suggestion_store(build_console_harness(build_console_ticket()))

    with pytest.raises(DatabaseUnavailableError):
        await build_get(harness).execute(SIGNED_IN_MANAGER, TICKET_ID)


async def test_unavailable_database_commits_no_view_and_records_no_event() -> None:
    harness = with_failing_suggestion_store(build_console_harness(build_console_ticket()))

    with pytest.raises(DatabaseUnavailableError):
        await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.TICKET_VIEWED) == ()
    assert harness.queue.notifications == []


async def test_unavailable_database_sends_no_reply_and_records_no_event() -> None:
    harness = with_failing_suggestion_store(build_console_harness(build_console_ticket()))

    with pytest.raises(DatabaseUnavailableError):
        await build_send(harness).execute(STAFF, TICKET_ID, REPLY, KEY)

    assert harness.replies.replies == {}
    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.REPLY_SENT) == ()


async def test_unavailable_proposal_store_stores_no_proposal_and_records_no_event() -> None:
    harness = build_console_harness(build_console_ticket())
    fail_proposal_store(harness)

    with pytest.raises(DatabaseUnavailableError):
        await build_propose(harness).execute(STAFF, TICKET_ID, REPLY, KEY)

    assert harness.proposals.proposals == {}
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.OPEN
    assert harness.audit.entries == []
    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.REPLY_PROPOSAL_SUBMITTED) == ()


async def test_unavailable_escalation_store_escalates_nothing_and_records_no_event() -> None:
    harness = build_console_harness(build_console_ticket())
    fail_escalation_store(harness)

    with pytest.raises(DatabaseUnavailableError):
        await build_escalate(harness).execute(STAFF, TICKET_ID, ESCALATION, KEY)

    assert harness.escalations.escalations == {}
    assert harness.replies.decisions == []
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.OPEN
    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.TICKET_ESCALATED) == ()
    assert harness.events.of(EventName.DECISION_RECORDED) == ()


async def test_unavailable_proposal_read_sends_no_reply_and_records_no_event() -> None:
    harness = build_console_harness(build_console_ticket(status=TicketStatus.AWAITING_APPROVAL))
    fail_proposal_store(harness)
    reply = ProposalReply("A manager approved your refund today.", "p-1")

    with pytest.raises(DatabaseUnavailableError):
        await build_send(harness).execute(MANAGER, TICKET_ID, reply, KEY)

    assert harness.replies.replies == {}
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.AWAITING_APPROVAL
    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.REPLY_SENT) == ()


@pytest.mark.parametrize(
    ("status", "fail_store"),
    [
        pytest.param(TicketStatus.AWAITING_APPROVAL, fail_proposal_store, id="proposal"),
        pytest.param(TicketStatus.ESCALATED, fail_escalation_store, id="escalation"),
    ],
)
async def test_unavailable_read_of_a_staff_action_reaches_the_workspace(
    status: TicketStatus, fail_store: Callable[[ConsoleHarness], None]
) -> None:
    harness = build_console_harness(build_console_ticket(status=status))
    fail_store(harness)

    with pytest.raises(DatabaseUnavailableError):
        await build_get(harness).execute(SIGNED_IN_MANAGER, TICKET_ID)
