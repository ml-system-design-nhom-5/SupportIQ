"""Integration tests of the health checks of the wired application (ERR-18)."""

from http import HTTPStatus

import pytest
from sqlalchemy.engine import make_url

from app.platform import EventName
from tests.integration.application import ORIGIN_HEADERS, build_settings, running_client
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

UNREACHABLE_URL = "postgresql+asyncpg://supportiq_app:x@127.0.0.1:1/supportiq"
UNKNOWN_DATABASE = "supportiq_no_such_database"


async def test_ready_answers_204_when_the_database_answers(
    worker_database: WorkerDatabase,
) -> None:
    events = RecordingEventRecorder()

    async with running_client(build_settings(worker_database), events, FakeClock()) as client:
        response = await client.get("/health/ready")

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert events.names()[0] is EventName.STARTUP_COMPLETED
    assert events.names()[-1] is EventName.SHUTDOWN_STARTED


async def test_ready_answers_503_not_ready_when_the_database_is_unreachable(
    worker_database: WorkerDatabase,
) -> None:
    settings = build_settings(worker_database, database_url_app=UNREACHABLE_URL)

    async with running_client(settings, RecordingEventRecorder(), FakeClock()) as client:
        response = await client.get("/health/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"


async def test_requests_answer_503_when_postgresql_refuses_the_connection(
    worker_database: WorkerDatabase,
) -> None:
    refused_url = make_url(worker_database.app_url).set(database=UNKNOWN_DATABASE)
    settings = build_settings(
        worker_database, database_url_app=refused_url.render_as_string(hide_password=False)
    )
    events = RecordingEventRecorder()

    async with running_client(settings, events, FakeClock()) as client:
        ready = await client.get("/health/ready")
        sign_in = await client.post(
            "/v1/sessions",
            json={"login_name": "staff-1", "password": "any-test-password"},
            headers=ORIGIN_HEADERS,
        )

    assert ready.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert sign_in.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert EventName.REQUEST_FAILED not in events.names()


async def test_live_answers_204_even_when_the_database_is_unreachable(
    worker_database: WorkerDatabase,
) -> None:
    settings = build_settings(worker_database, database_url_app=UNREACHABLE_URL)

    async with running_client(settings, RecordingEventRecorder(), FakeClock()) as client:
        response = await client.get("/health/live")

    assert response.status_code == HTTPStatus.NO_CONTENT
