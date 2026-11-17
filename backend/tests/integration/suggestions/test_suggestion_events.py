"""The suggestion progress stream over HTTP (`getSuggestionEvents`, ADR-0022).

The test client collects the whole body before it returns, so every stream here ends by
itself: at a short time limit, or after the event that shows no pending part. The fake clock
ends each wait at once, unless a test holds it to act between two reads.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from http import HTTPStatus

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.platform import EventName
from supportiq_backend.suggestions import (
    SuggestionId,
    SuggestionTicketId,
    build_analysis_completion,
    build_draft_completion,
)
from tests.integration.application import build_settings, running_client
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.integration.suggestions.read_requests import (
    SignIn,
    headers_of,
    problem_example,
    problem_of,
    sign_in_as_admin,
    sign_in_as_customer,
)
from tests.integration.tickets.console_requests import sign_in_as_manager, sign_in_as_support
from tests.integration.workflow.workflow_rows import (
    complete_parts,
    insert_ticket,
    received_analysis_example,
    received_draft_example,
    set_handling_mode,
    set_ticket_status,
    start_suggestion,
    ticket_created,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START, FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

# Long enough for one ping comment after 15 s without an event.
TIME_LIMIT_MS = 20_000
RETRY = "retry: 3000\n\n"
PING = ": ping\n\n"
UNKNOWN_TICKET_ID = "TCK-9999"


class HeldClock(FakeClock):
    """A fake clock whose waits end only when the test lets the next one end."""

    def __init__(self) -> None:
        """Start the clock with no wait running."""
        super().__init__()
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    async def sleep(self, duration_ms: int) -> None:
        """Tell the test that a wait started, then wait until it is released."""
        self.waiting.set()
        await self.release.wait()
        self.release.clear()
        await super().sleep(duration_ms)


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


def events_path(ticket_id: str) -> str:
    return f"/v1/console/tickets/{ticket_id}/suggestion-events"


def event(suggestion_id: SuggestionId, analysis_status: str, draft_status: str) -> str:
    data = json.dumps(
        {
            "suggestion_id": suggestion_id,
            "analysis_status": analysis_status,
            "draft_status": draft_status,
        },
        separators=(",", ":"),
    )
    return f"event: suggestion\ndata: {data}\n\n"


async def pending_ticket(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> tuple[SuggestionTicketId, SuggestionId]:
    ticket_id = await insert_ticket(builder)
    return ticket_id, await start_suggestion(app_engine, builder, ticket_created(ticket_id))


async def complete_both_parts(app_engine: AsyncEngine, suggestion_id: SuggestionId) -> None:
    await complete_parts(
        app_engine,
        suggestion_id,
        build_analysis_completion(received_analysis_example("draft"), FAKE_CLOCK_START),
        build_draft_completion(received_draft_example("draft-ready"), FAKE_CLOCK_START),
    )


async def follow(
    worker_database: WorkerDatabase, path: str, headers: dict[str, str]
) -> tuple[httpx.Response, RecordingEventRecorder]:
    events = RecordingEventRecorder()
    settings = build_settings(worker_database, suggestion_events_max_ms=TIME_LIMIT_MS)
    async with running_client(settings, events, FakeClock()) as client:
        response = await client.get(path, headers=headers)
    return response, events


@pytest.mark.parametrize(
    "sign_in",
    [headers_of(sign_in_as_support), headers_of(sign_in_as_manager)],
    ids=["staff", "manager"],
)
async def test_staff_and_managers_get_the_current_state_then_a_ping_until_the_time_limit(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    sign_in: SignIn,
) -> None:
    ticket_id, suggestion_id = await pending_ticket(app_engine, builder)

    response, events = await follow(worker_database, events_path(ticket_id), await sign_in(builder))

    (ended,) = events.of(EventName.SUGGESTION_STREAM_ENDED)
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.text == RETRY + event(suggestion_id, "pending", "pending") + PING
    assert ended.attributes["stream_end_reason"] == "time_limit"


async def test_a_stored_result_sends_its_event_and_ends_the_stream(
    worker_database: WorkerDatabase, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id, suggestion_id = await pending_ticket(app_engine, builder)
    headers = (await sign_in_as_support(builder)).headers
    events = RecordingEventRecorder()
    clock = HeldClock()

    async with running_client(build_settings(worker_database), events, clock) as client:
        request = asyncio.create_task(client.get(events_path(ticket_id), headers=headers))
        await clock.waiting.wait()
        await complete_both_parts(app_engine, suggestion_id)
        clock.release.set()
        response = await request

    (ended,) = events.of(EventName.SUGGESTION_STREAM_ENDED)
    assert response.text == (
        RETRY
        + event(suggestion_id, "pending", "pending")
        + event(suggestion_id, "ready", "draft_ready")
    )
    assert ended.attributes["stream_end_reason"] == "no_pending_part"


async def test_a_ticket_that_left_open_gets_204(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    builder: DatabaseBuilder,
) -> None:
    ticket_id, _ = await pending_ticket(app_engine, builder)
    await set_ticket_status(owner_engine, ticket_id, "escalated")
    headers = (await sign_in_as_manager(builder)).headers

    response, _ = await follow(worker_database, events_path(ticket_id), headers)

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""


async def test_a_ticket_in_manual_mode_gets_204(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    builder: DatabaseBuilder,
) -> None:
    ticket_id, _ = await pending_ticket(app_engine, builder)
    await set_handling_mode(owner_engine, ticket_id, "manual")
    headers = (await sign_in_as_support(builder)).headers

    response, _ = await follow(worker_database, events_path(ticket_id), headers)

    assert response.status_code == HTTPStatus.NO_CONTENT


async def test_a_suggestion_without_a_pending_part_gets_204(
    worker_database: WorkerDatabase, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id, suggestion_id = await pending_ticket(app_engine, builder)
    await complete_both_parts(app_engine, suggestion_id)
    headers = (await sign_in_as_support(builder)).headers

    response, _ = await follow(worker_database, events_path(ticket_id), headers)

    assert response.status_code == HTTPStatus.NO_CONTENT


@pytest.mark.parametrize("sign_in", [sign_in_as_customer, sign_in_as_admin])
async def test_customers_and_admins_get_403(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    sign_in: SignIn,
) -> None:
    ticket_id, _ = await pending_ticket(app_engine, builder)

    response, events = await follow(worker_database, events_path(ticket_id), await sign_in(builder))

    (denied,) = events.of(EventName.PERMISSION_DENIED)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert problem_of(response) == problem_example("forbidden-role")
    assert denied.attributes["operation_id"] == "getSuggestionEvents"


async def test_a_request_without_a_session_gets_401(
    worker_database: WorkerDatabase, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id, _ = await pending_ticket(app_engine, builder)

    response, _ = await follow(worker_database, events_path(ticket_id), {})

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert problem_of(response) == problem_example("unauthenticated")


async def test_an_unknown_ticket_gets_404(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers

    response, _ = await follow(worker_database, events_path(UNKNOWN_TICKET_ID), headers)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert problem_of(response) == problem_example("not-found")
