"""Recording a ticket view over HTTP against PostgreSQL (`recordTicketView`).

The first view of an open ticket in `assisted` mode reads the KB version of ai-service. These
tests run ai-service on a loopback port where nothing listens, so the read fails at once and
the view is still recorded (backend ticket workflow design, Views).
"""

from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest

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
# Nothing listens on port 1 of the loopback address, so a connection is refused at once.
UNREACHABLE_AI_SERVICE_URL = "http://127.0.0.1:1"


@pytest.fixture
async def backend_without_ai_service(
    worker_database: WorkerDatabase,
) -> AsyncIterator[RunningBackend]:
    """Run the application with an ai-service that refuses every connection.

    Args:
        worker_database: The database of the worker.

    Yields:
        The running application with its fake clock and its recorded events.
    """
    clock = FakeClock()
    events = RecordingEventRecorder()
    settings = build_settings(worker_database, ai_service_base_url=UNREACHABLE_AI_SERVICE_URL)
    async with running_client(settings, events, clock) as client:
        yield RunningBackend(client, clock, events)


async def test_first_view_returns_204_without_a_body(
    backend_without_ai_service: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)

    response = await backend_without_ai_service.client.post(
        ticket_path(ticket.ticket_id, VIEWS), headers=key_headers(headers)
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""


async def test_first_view_starts_the_handling_clock_while_ai_service_is_down(
    backend_without_ai_service: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)

    await backend_without_ai_service.client.post(
        ticket_path(ticket.ticket_id, VIEWS), headers=key_headers(headers)
    )

    started_at = await builder.scalar(
        "SELECT handling_started_at FROM tickets WHERE ticket_id = :ticket_id",
        ticket_id=ticket.ticket_id,
    )
    assert started_at == FAKE_CLOCK_START


async def test_repeated_view_with_the_same_key_returns_204_again(
    backend_without_ai_service: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    path = ticket_path(ticket.ticket_id, VIEWS)
    await backend_without_ai_service.client.post(path, headers=key_headers(headers))

    repeated = await backend_without_ai_service.client.post(path, headers=key_headers(headers))

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
