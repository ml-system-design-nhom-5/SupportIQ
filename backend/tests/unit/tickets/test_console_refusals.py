"""Refusals and failures of the console use cases with fakes of every port (SEC-41, ERR-15).

Customers and admins never reach a console use case, and an unknown ticket, a reused
`Idempotency-Key`, or an unavailable database changes nothing and records no event of success
(backend ticket workflow design, Ticket state machine and check order).
"""

import pytest

from supportiq_backend.accounts import ForbiddenRoleError, Principal
from supportiq_backend.idempotency import IdempotencyKeyReusedError
from supportiq_backend.platform import DatabaseUnavailableError, EventName
from supportiq_backend.tickets import NoAiDraftReply, TicketId, TicketNotFoundError, TicketStatus
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
    build_get,
    build_list,
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


def with_failing_suggestion_store(harness: ConsoleHarness) -> ConsoleHarness:
    with_suggestion(harness, build_ready_suggestion())
    harness.suggestions.failure = DatabaseUnavailableError()
    return harness


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
