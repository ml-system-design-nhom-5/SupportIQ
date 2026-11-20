"""Reading a KB document version over HTTP (`getConsoleKbDocumentVersion`, UI-20, SEC-41).

The ai-service of these tests is an in-memory one that answers with the examples of its
contract, answers with an error, or refuses every connection. The document reaches the console
as ai-service serves it; a `404` of ai-service is a `404`. An ai-service that cannot answer is
`503 not-ready`, logged once as `ai_service.call_failed`, and a response outside the contract is
`500`, logged once as `ai_service.contract_violated` (backend ticket workflow design, The
`ai-service` client; ERR-05).
"""

from http import HTTPStatus

import pytest

from app.platform import EventName
from tests.integration.ai_service_doubles import (
    Answer,
    FakeAiService,
    answer_with,
    read_example,
    refuse_connection,
)
from tests.integration.application import (
    ORIGIN_HEADERS,
    RunningBackend,
    build_settings,
    running_client,
)
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.suggestions.read_requests import (
    SignIn,
    headers_of,
    problem_example,
    problem_of,
    sign_in_as_admin,
    sign_in_as_customer,
)
from tests.integration.tickets.console_requests import sign_in_as_manager, sign_in_as_support
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

DOCUMENT_PATH = "/v1/console/kb-documents/SAMPLE-REFUND-001/versions/1.0"
AI_SERVICE_DOCUMENT_PATH = "/v1/kb-documents/SAMPLE-REFUND-001/versions/1.0"
FOUND = "getKbDocumentVersion/found.json"
LAST_REVIEWED_AT = "2026-06-30T12:00:00Z"
# Paths whose `document_id` or `version` is outside the pattern of the contract.
PATHS_OUTSIDE_THE_PATTERN = [
    "/v1/console/kb-documents/.hidden/versions/1.0",
    "/v1/console/kb-documents/" + "A" * 65 + "/versions/1.0",
    "/v1/console/kb-documents/SAMPLE-REFUND-001/versions/-1",
    "/v1/console/kb-documents/SAMPLE-REFUND-001/versions/1%200",
]
OUTSIDE_IDS = ["leading-dot", "too-long", "leading-dash", "space"]
# A connection error and a `5xx`: the failures of an ai-service that cannot answer.
CANNOT_ANSWER: list[Answer] = [
    refuse_connection,
    answer_with(read_example("problems/internal-error.json"), HTTPStatus.INTERNAL_SERVER_ERROR),
]
CANNOT_ANSWER_IDS = ["connection-refused", "5xx"]
FAILURE_EVENTS = (
    EventName.AI_SERVICE_CALL_FAILED,
    EventName.AI_SERVICE_CONTRACT_VIOLATED,
    EventName.DATABASE_CALL_FAILED,
    EventName.REQUEST_FAILED,
)


def failures_of(events: RecordingEventRecorder) -> list[EventName]:
    return [name for name in events.names() if name in FAILURE_EVENTS]


@pytest.mark.parametrize(
    "sign_in",
    [headers_of(sign_in_as_support), headers_of(sign_in_as_manager)],
    ids=["staff", "manager"],
)
async def test_staff_and_managers_get_the_document_version_as_ai_service_serves_it(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, sign_in: SignIn
) -> None:
    ai_service = FakeAiService(answer_with(read_example(FOUND)))
    headers = await sign_in(builder)

    async with running_client(
        build_settings(worker_database),
        RecordingEventRecorder(),
        FakeClock(),
        ai_service=ai_service,
    ) as client:
        response = await client.get(DOCUMENT_PATH, headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"
    assert response.json() == read_example(FOUND)
    assert ai_service.paths() == [AI_SERVICE_DOCUMENT_PATH]


async def test_every_optional_field_that_ai_service_sends_reaches_the_console(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    document = read_example("getConsoleKbDocumentVersion/document-version.json") | {
        "last_reviewed_at": LAST_REVIEWED_AT
    }
    headers = (await sign_in_as_support(builder)).headers

    async with running_client(
        build_settings(worker_database),
        RecordingEventRecorder(),
        FakeClock(),
        ai_service=FakeAiService(answer_with(document)),
    ) as client:
        response = await client.get(DOCUMENT_PATH, headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == document


@pytest.mark.parametrize("sign_in", [sign_in_as_customer, sign_in_as_admin])
async def test_customers_and_admins_get_403_and_ai_service_is_not_read(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, sign_in: SignIn
) -> None:
    ai_service = FakeAiService(answer_with(read_example(FOUND)))
    events = RecordingEventRecorder()
    headers = await sign_in(builder)

    async with running_client(
        build_settings(worker_database), events, FakeClock(), ai_service=ai_service
    ) as client:
        response = await client.get(DOCUMENT_PATH, headers=headers)

    (denied,) = events.of(EventName.PERMISSION_DENIED)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert problem_of(response) == problem_example("forbidden-role")
    assert denied.attributes["operation_id"] == "getConsoleKbDocumentVersion"
    assert ai_service.requests == []


async def test_an_admin_gets_403_even_for_a_path_outside_the_pattern(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = await sign_in_as_admin(builder)

    response = await backend.client.get(PATHS_OUTSIDE_THE_PATTERN[0], headers=headers)

    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize("path", PATHS_OUTSIDE_THE_PATTERN, ids=OUTSIDE_IDS)
async def test_a_path_outside_the_pattern_is_404_and_ai_service_is_not_read(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, path: str
) -> None:
    ai_service = FakeAiService(answer_with(read_example(FOUND)))
    headers = (await sign_in_as_support(builder)).headers

    async with running_client(
        build_settings(worker_database),
        RecordingEventRecorder(),
        FakeClock(),
        ai_service=ai_service,
    ) as client:
        response = await client.get(path, headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert problem_of(response) == problem_example("not-found")
    assert ai_service.requests == []


async def test_a_version_that_ai_service_does_not_know_is_404_without_a_failure(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    not_found = read_example("problems/not-found.json")
    events = RecordingEventRecorder()
    headers = (await sign_in_as_support(builder)).headers

    async with running_client(
        build_settings(worker_database),
        events,
        FakeClock(),
        ai_service=FakeAiService(answer_with(not_found, HTTPStatus.NOT_FOUND)),
    ) as client:
        response = await client.get(DOCUMENT_PATH, headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert problem_of(response) == problem_example("not-found")
    assert failures_of(events) == []


@pytest.mark.parametrize("answer", CANNOT_ANSWER, ids=CANNOT_ANSWER_IDS)
async def test_an_ai_service_that_cannot_answer_is_503_logged_once(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, answer: Answer
) -> None:
    ai_service = FakeAiService(answer)
    events = RecordingEventRecorder()
    headers = (await sign_in_as_support(builder)).headers

    async with running_client(
        build_settings(worker_database), events, FakeClock(), ai_service=ai_service
    ) as client:
        response = await client.get(DOCUMENT_PATH, headers=headers)

    (failure,) = events.of(EventName.AI_SERVICE_CALL_FAILED)
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert problem_of(response) == problem_example("ai-service-not-ready")
    assert failure.attributes == {"ai_service_operation": "getKbDocumentVersion"}
    assert failures_of(events) == [EventName.AI_SERVICE_CALL_FAILED]
    assert ai_service.paths() == [AI_SERVICE_DOCUMENT_PATH]


async def test_a_document_version_outside_the_contract_is_500_logged_once(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    outside = read_example(FOUND) | {"title": 7}
    events = RecordingEventRecorder()
    headers = (await sign_in_as_support(builder)).headers

    async with running_client(
        build_settings(worker_database),
        events,
        FakeClock(),
        ai_service=FakeAiService(answer_with(outside)),
    ) as client:
        response = await client.get(DOCUMENT_PATH, headers=headers)

    (failure,) = events.of(EventName.AI_SERVICE_CONTRACT_VIOLATED)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert problem_of(response) == problem_example("internal-error")
    assert failure.attributes == {"ai_service_operation": "getKbDocumentVersion"}
    assert failures_of(events) == [EventName.AI_SERVICE_CONTRACT_VIOLATED]


async def test_a_read_without_a_session_is_401(backend: RunningBackend) -> None:
    response = await backend.client.get(DOCUMENT_PATH, headers=ORIGIN_HEADERS)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
