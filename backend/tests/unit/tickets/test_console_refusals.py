"""Refusals and failures of the console use cases with fakes of every port (SEC-41, ERR-15).

Customers and admins never reach a console use case, and an unknown ticket, a reused
`Idempotency-Key`, or an unavailable database changes nothing and records no event of success
(backend ticket workflow design, Ticket state machine and check order).
"""

import json
from dataclasses import replace
from uuid import UUID

import pytest

from supportiq_backend.accounts import (
    AccountId,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
    Principal,
    SupportPrincipal,
    SupportRole,
)
from supportiq_backend.commerce import OrderId
from supportiq_backend.idempotency import IdempotencyKey, IdempotencyKeyReusedError, StoredResponse
from supportiq_backend.platform import DatabaseUnavailableError, EventName
from supportiq_backend.tickets import (
    ConsoleTicket,
    GetConsoleTicket,
    HandlingMode,
    ListConsoleTickets,
    NoAiDraftReply,
    RecordTicketView,
    ReplyRecord,
    SendReply,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START
from tests.unit.pseudonymization.fakes import CUSTOMER_ID
from tests.unit.suggestions.builders import (
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    build_ready_suggestion,
)
from tests.unit.tickets.console_fakes import ConsoleHarness, build_console_harness

pytestmark = pytest.mark.anyio

TICKET_ID = TicketId("TCK-1042")
OTHER_TICKET_ID = TicketId("TCK-1043")
UNKNOWN_TICKET_ID = TicketId("TCK-9999")
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000456"))
STAFF = SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.STAFF)
MANAGER = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.MANAGER)
CUSTOMER = CustomerPrincipal(AccountId("00000000-0000-4000-8000-0000000000cc"), CUSTOMER_ID)
ADMIN = InternalPrincipal(AccountId("00000000-0000-4000-8000-0000000000ad"), InternalRole.ADMIN)
REFUSED_ROLES = [(CUSTOMER, "customer"), (ADMIN, "admin")]
PAGE_LIMIT = 10
REPLY = NoAiDraftReply("Your parcel left our warehouse today.", None)
OTHER_REPLY = NoAiDraftReply("Your parcel arrives tomorrow.", None)


def build_ticket(ticket_id: TicketId = TICKET_ID) -> ConsoleTicket:
    return ConsoleTicket(
        ticket_id=ticket_id,
        status=TicketStatus.OPEN,
        handling_mode=HandlingMode.ASSISTED,
        is_authority_required=False,
        created_at=FAKE_CLOCK_START,
        handling_started_at=None,
        closed_at=None,
        customer_id=CUSTOMER_ID,
        order_id=OrderId("ORD-20901"),
        current_suggestion_id=None,
        message="Where is my parcel?",
    )


def with_current_suggestion(ticket: ConsoleTicket) -> ConsoleTicket:
    return replace(ticket, current_suggestion_id=SUGGESTION_ID)


def with_failing_suggestion_store(harness: ConsoleHarness) -> ConsoleHarness:
    harness.suggestions.data.add(build_ready_suggestion())
    harness.suggestions.failure = DatabaseUnavailableError()
    return harness


def render_reply(record: ReplyRecord) -> StoredResponse:
    return StoredResponse(201, json.dumps({"reply_id": str(record.reply.reply_id)}))


def build_send(harness: ConsoleHarness) -> SendReply:
    return SendReply(harness.transactions, harness.ports, render_reply)


def build_view(harness: ConsoleHarness) -> RecordTicketView:
    return RecordTicketView(harness.transactions, harness.ports)


@pytest.mark.parametrize(("principal", "role"), REFUSED_ROLES)
async def test_list_console_tickets_refuses_customers_and_admins_and_records_it(
    principal: Principal, role: str
) -> None:
    harness = build_console_harness(build_ticket())

    with pytest.raises(ForbiddenRoleError):
        ListConsoleTickets(harness.transactions, harness.ports).authorize(principal)

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
    harness = build_console_harness(build_ticket())

    with pytest.raises(ForbiddenRoleError):
        await GetConsoleTicket(harness.transactions, harness.ports).execute(principal, TICKET_ID)

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
    harness = build_console_harness(build_ticket())

    with pytest.raises(ForbiddenRoleError):
        build_view(harness).authorize(principal)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert (denied.attributes["role"], denied.attributes["operation_id"]) == (
        role,
        "recordTicketView",
    )


async def test_record_ticket_view_returns_a_manager_as_support() -> None:
    harness = build_console_harness(build_ticket())

    support = build_view(harness).authorize(MANAGER)

    assert support == SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.MANAGER)
    assert harness.events.of(EventName.PERMISSION_DENIED) == ()


async def test_workspace_of_an_unknown_ticket_is_not_found() -> None:
    harness = build_console_harness(build_ticket())

    with pytest.raises(TicketNotFoundError):
        await GetConsoleTicket(harness.transactions, harness.ports).execute(
            MANAGER, UNKNOWN_TICKET_ID
        )


async def test_view_of_an_unknown_ticket_is_not_found_and_records_nothing() -> None:
    harness = build_console_harness(build_ticket())

    with pytest.raises(TicketNotFoundError):
        await build_view(harness).execute(STAFF, UNKNOWN_TICKET_ID, KEY)

    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.TICKET_VIEWED) == ()


async def test_reply_to_an_unknown_ticket_is_not_found_and_sends_nothing() -> None:
    harness = build_console_harness(build_ticket())

    with pytest.raises(TicketNotFoundError):
        await build_send(harness).execute(STAFF, UNKNOWN_TICKET_ID, REPLY, KEY)

    assert harness.replies.replies == {}
    assert harness.transactions.commit_count == 0


async def test_view_key_reused_on_another_ticket_is_refused_and_starts_no_clock() -> None:
    harness = build_console_harness(build_ticket(), build_ticket(OTHER_TICKET_ID))
    view = build_view(harness)
    await view.execute(STAFF, TICKET_ID, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await view.execute(STAFF, OTHER_TICKET_ID, KEY)

    assert harness.tickets.tickets[OTHER_TICKET_ID].handling_started_at is None
    assert len(harness.events.of(EventName.TICKET_VIEWED)) == 1


async def test_reply_key_reused_with_another_body_is_refused_and_keeps_the_first_reply() -> None:
    harness = build_console_harness(build_ticket())
    send = build_send(harness)
    await send.execute(STAFF, TICKET_ID, REPLY, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await send.execute(STAFF, TICKET_ID, OTHER_REPLY, KEY)

    assert harness.replies.replies[TICKET_ID].body == REPLY.body
    assert len(harness.events.of(EventName.REPLY_SENT)) == 1


async def test_unavailable_database_reaches_the_queue() -> None:
    harness = with_failing_suggestion_store(
        build_console_harness(with_current_suggestion(build_ticket()))
    )

    with pytest.raises(DatabaseUnavailableError):
        await ListConsoleTickets(harness.transactions, harness.ports).execute(
            MANAGER, TicketStatus.OPEN, None, PAGE_LIMIT
        )


async def test_unavailable_database_reaches_the_workspace() -> None:
    harness = with_failing_suggestion_store(
        build_console_harness(with_current_suggestion(build_ticket()))
    )

    with pytest.raises(DatabaseUnavailableError):
        await GetConsoleTicket(harness.transactions, harness.ports).execute(MANAGER, TICKET_ID)


async def test_unavailable_database_commits_no_view_and_records_no_event() -> None:
    harness = with_failing_suggestion_store(
        build_console_harness(with_current_suggestion(build_ticket()))
    )

    with pytest.raises(DatabaseUnavailableError):
        await build_view(harness).execute(STAFF, TICKET_ID, KEY)

    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.TICKET_VIEWED) == ()
    assert harness.queue.notifications == []


async def test_unavailable_database_sends_no_reply_and_records_no_event() -> None:
    harness = with_failing_suggestion_store(
        build_console_harness(with_current_suggestion(build_ticket()))
    )

    with pytest.raises(DatabaseUnavailableError):
        await build_send(harness).execute(STAFF, TICKET_ID, REPLY, KEY)

    assert harness.replies.replies == {}
    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.REPLY_SENT) == ()
