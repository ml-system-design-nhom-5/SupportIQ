"""Recording a ticket view over HTTP against PostgreSQL (`recordTicketView`).

The first view of an open ticket in `assisted` mode that has a current suggestion reads the KB
version of ai-service; a ticket without a suggestion reads nothing. The ai-service of these
tests is an in-memory one that refuses every connection, so that read fails at once and the
view is still recorded (backend ticket workflow design, Views).
"""

from http import HTTPStatus

import pytest

from app.platform import EventName
from tests.integration.ai_service_doubles import FakeAiService, refuse_connection
from tests.integration.application import (
    ORIGIN_HEADERS,
    RunningBackend,
    build_settings,
    running_client,
)
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.tickets.console_requests import (
    INVALID_KEY_HEADERS,
    INVALID_KEY_IDS,
    UNKNOWN_TICKET_ID,
    key_headers,
    open_ticket,
    sign_in_as_support,
    ticket_path,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START, FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

VIEWS = "/views"
ASSET_VERSIONS_PATH = "/v1/asset-versions"
GET_ASSET_VERSIONS = "getAssetVersions"
HANDLING_STARTED_AT = "SELECT handling_started_at FROM tickets WHERE ticket_id = :ticket_id"


async def test_first_view_returns_204_without_a_body(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, VIEWS), headers=key_headers(headers)
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""


async def test_first_view_is_recorded_while_ai_service_refuses_the_kb_read(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    ai_service = FakeAiService(refuse_connection)
    events = RecordingEventRecorder()
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    # Only a first view of a ticket with a current suggestion reads the KB version.
    await builder.suggestion(ticket.ticket_id)
    settings = build_settings(worker_database)

    async with running_client(settings, events, FakeClock(), ai_service=ai_service) as client:
        response = await client.post(
            ticket_path(ticket.ticket_id, VIEWS), headers=key_headers(headers)
        )

    started_at = await builder.scalar(HANDLING_STARTED_AT, ticket_id=ticket.ticket_id)
    (failure,) = events.of(EventName.AI_SERVICE_CALL_FAILED)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""
    assert ai_service.paths() == [ASSET_VERSIONS_PATH]
    assert failure.attributes["ai_service_operation"] == GET_ASSET_VERSIONS
    assert started_at == FAKE_CLOCK_START


async def test_repeated_view_with_the_same_key_returns_204_again(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    path = ticket_path(ticket.ticket_id, VIEWS)
    await backend.client.post(path, headers=key_headers(headers))

    repeated = await backend.client.post(path, headers=key_headers(headers))

    assert repeated.status_code == HTTPStatus.NO_CONTENT


@pytest.mark.parametrize("key_header", INVALID_KEY_HEADERS, ids=INVALID_KEY_IDS)
async def test_missing_or_invalid_key_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, key_header: dict[str, str]
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, VIEWS), headers={**headers, **key_header}
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_view_of_an_unknown_ticket_returns_404(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers

    response = await backend.client.post(
        ticket_path(UNKNOWN_TICKET_ID, VIEWS), headers=key_headers(headers)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_view_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.post(
        ticket_path(UNKNOWN_TICKET_ID, VIEWS), headers=key_headers(ORIGIN_HEADERS)
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
